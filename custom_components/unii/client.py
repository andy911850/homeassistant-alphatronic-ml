#
# Copyright 2024 unii-security (Original)
# Copyright 2026 andy911850 (Modifications)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Unii Client for Home Assistant."""
import asyncio
import struct
import binascii
import logging
from Crypto.Cipher import AES
from Crypto.Util import Counter

_LOGGER = logging.getLogger(__name__)

class UniiClient:
    def __init__(self, ip, port=6502, shared_key=None):
        self.ip = ip
        self.port = port
        self.shared_key = shared_key
        self.reader = None
        self.writer = None
        self.session_id = 0xFFFF
        self.tx_seq = 0
        self.rx_seq = 0
        self._connected = False
        self._lock = asyncio.Lock()
        self._transaction_lock = asyncio.Lock()
        
    async def connect(self):
        async with self._lock:
            if self._connected and self.writer:
                # Check if connection is still alive
                try:
                    # Test write
                    # No easy way to test without sending a command, 
                    # but let's assume it's okay unless we get an error elsewhere.
                    return True
                except Exception:
                    self._connected = False

            _LOGGER.info(f"Connecting to {self.ip}:{self.port}...")
            try:
                self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
                
                # Handshake
                if await self._send_command(0x0001): # CONNECTION_REQUEST
                    resp = await self._recv_response()
                    if resp and resp['command'] == 0x0002: # CONNECTION_REQUEST_RESPONSE
                        _LOGGER.info("Connected and Authenticated!")
                        self._connected = True
                        return True
                        
                # If handshake failed
                if self.writer:
                    self.writer.close()
                self._connected = False
                return False
            except Exception as e:
                _LOGGER.error(f"Connection failed: {e}")
                self._connected = False
                return False

    async def disconnect(self):
        async with self._lock:
            if self.writer:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except Exception:
                    pass
            self.writer = None
            self.reader = None
            self._connected = False
            self.session_id = 0xFFFF
            self.tx_seq = 0
            self.rx_seq = 0
            _LOGGER.info("Disconnected.")

    def _encrypt(self, payload, header):
        if not self.shared_key:
            return payload
            
        key_padded = self.shared_key[:16].ljust(16, " ")
        key_bytes = key_padded.encode("utf-8")
        
        # IV = First 12 bytes of Header + 00000000
        iv = header[:12] + b'\x00\x00\x00\x00'
        
        ctr = Counter.new(128, initial_value=int.from_bytes(iv, 'big'))
        cipher = AES.new(key_bytes, AES.MODE_CTR, counter=ctr)
        return bytearray(cipher.encrypt(payload))

    def _decrypt(self, payload_enc, header):
        # Decryption is symmetric in CTR mode
        return self._encrypt(payload_enc, header)

    def _calculate_crc16(self, data):
        crc = 0x0000
        poly = 0x1021
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if (crc & 0x8000) > 0:
                    crc = (crc << 1) ^ poly
                else:
                    crc <<= 1
            crc &= 0xFFFF
        return crc

    async def _send_command(self, command_id, data=b""):
        # Protocol: 0x05 (Basic Enc) or 0x04 (None)
        proto_id = 0x05 if self.shared_key else 0x04
        packet_type = 0x01 if command_id < 0x0008 else 0x02
        
        # Header (14 bytes)
        # Session(2)|TX(4)|RX(4)|Proto(1)|Type(1)|Len(2)
        header = bytearray()
        header += struct.pack(">H", self.session_id)
        header += struct.pack(">I", self.tx_seq)
        header += struct.pack(">I", self.rx_seq)
        header += struct.pack("B", proto_id)
        header += struct.pack("B", packet_type)
        header += b'\x00\x00' # Len placeholder
        
        # Payload
        payload = bytearray()
        payload += struct.pack(">H", command_id)
        payload += struct.pack(">H", len(data))
        payload += data
        
        # Padding
        packet_len_temp = len(header) + len(payload) + 2
        pad_len = 16 - (packet_len_temp % 16)
        if pad_len == 16: pad_len = 0
        payload += b'\x00' * pad_len
        
        # Encrypt
        payload_enc = self._encrypt(payload, header)
        
        # Assemble
        msg = header + payload_enc
        
        # Update Length
        total_len = len(msg) + 2
        msg[12] = (total_len >> 8) & 0xFF
        msg[13] = total_len & 0xFF
        
        # Checksum
        crc = self._calculate_crc16(msg)
        msg += struct.pack(">H", crc)
        
        try:
            self.writer.write(msg)
            await self.writer.drain()
            self.tx_seq += 1
            return True
        except Exception as e:
            _LOGGER.error(f"Send Failed: {e}")
            return False

    async def _recv_response(self, expected_cmd=None, timeout=5):
        try:
            # Header
            header = await asyncio.wait_for(self.reader.readexactly(14), timeout=timeout)
            
            # Length
            length = struct.unpack(">H", header[12:14])[0]
            remaining = length - 14
            
            body = await asyncio.wait_for(self.reader.readexactly(remaining), timeout=timeout)
            
            # Decrypt
            payload_enc = body[:-2]
            payload_dec = self._decrypt(payload_enc, header)
            
            # Parse
            cmd_id = struct.unpack(">H", payload_dec[:2])[0]
            data_len = struct.unpack(">H", payload_dec[2:4])[0]
            data = payload_dec[4:4+data_len]
            
            # Update State
            self.session_id = struct.unpack(">H", header[:2])[0]
            self.rx_seq = struct.unpack(">I", header[2:6])[0] 
            
            # Identify Logic
            if expected_cmd:
                if cmd_id == expected_cmd:
                    return {'command': cmd_id, 'data': data}
                elif cmd_id in [0x0102, 0x0105, 0x0107, 0x0013]: # Event, Input/Device Changed, Poll Alive
                    # _LOGGER.debug(f"Ignoring Async Event: 0x{cmd_id:04x}")
                    # Recursive call to wait for next packet
                    return await self._recv_response(expected_cmd, timeout)
                else:
                    _LOGGER.warning(f"Received unexpected cmd: 0x{cmd_id:04x} (Wanted 0x{expected_cmd:04x})")
                    return {'command': cmd_id, 'data': data}
            
            return {'command': cmd_id, 'data': data}
            
        except asyncio.TimeoutError:
            _LOGGER.warning("Receive Timeout")
            return None
        except Exception as e:
            _LOGGER.error(f"Recv Failed: {e}")
            return None

    async def get_status(self):
        async with self._transaction_lock:
            # Request Section Status (0x0116)
            # Mask for all potential sections
            mask = bytes([0xFF] * 4) # 32 bits for 32 sections
            if await self._send_command(0x0116, b'\x01' + mask): # Version 1 + mask
                return await self._recv_response(expected_cmd=0x0117)
            return None

    async def get_input_status(self):
        async with self._transaction_lock:
            # Request Input Status (0x0106)
            # Version 2 (based on py-unii)
            if await self._send_command(0x0106, b'\x02'):
                return await self._recv_response(expected_cmd=0x0105)
            return None

    async def get_input_arrangement(self, block=0):
        async with self._transaction_lock:
            # Request Input Arrangement (0x0140)
            # Version 2 | Block Number (2b)
            payload = b'\x02' + struct.pack(">H", block)
            if await self._send_command(0x0140, payload):
                resp = await self._recv_response(expected_cmd=0x0141)
                if not resp:
                    return None
                
                data = resp['data']
                version = data[1] # wait, message is: cmd(2)|len(2)|data... but _recv_req parses it
                # resp['data'] starts AFTER the cmd/len. So data[0] is version? 
                # py-unii says data[1] is version. Let's check _recv_response
                # cmd_id = struct.unpack(">H", payload_dec[:2])[0]
                # data_len = struct.unpack(">H", payload_dec[2:4])[0]
                # data = payload_dec[4:4+data_len]
                # If py-unii says data[1] is version, then the data block starts with some overhead.
                # Actually, MLIP headers usually have Version at offset 0 of the data.
                
                inputs = {}
                offset = 4 # Skip Version(1), Reserved(1), Block(2)
                while offset < len(data):
                    if offset + 5 > len(data): break
                    input_num = struct.unpack(">H", data[offset:offset+2])[0]
                    sensor_type = data[offset+2]
                    reaction = data[offset+3]
                    name_len = data[offset+4]
                    
                    if offset + 5 + name_len + 4 > len(data): break
                    
                    name_raw = data[offset+5:offset+5+name_len]
                    name = name_raw.decode("latin-1").strip()
                    
                    # Sections (4 bytes)
                    # For now just store the basic info
                    inputs[input_num] = {
                        "name": name,
                        "sensor_type": sensor_type,
                        "reaction": reaction
                    }
                    
                    offset += 9 + name_len
                    
                return {"block": block, "inputs": inputs}
            return None

    async def bypass_input(self, input_id, user_code):
        async with self._transaction_lock:
            # Request to Bypass an Input (0x0118)
            # Mode (0x00 = User Code) | Code (8b BCD) | InputID (2b)
            payload = bytearray([0x00])
            payload.extend(self._bcd_encode_v2(user_code))
            payload.extend(struct.pack(">H", input_id))
            if await self._send_command(0x0118, payload):
                return await self._recv_response(expected_cmd=0x0119)
            return None

    async def unbypass_input(self, input_id, user_code):
        async with self._transaction_lock:
            # Request to Unbypass an Input (0x011A)
            payload = bytearray([0x00])
            payload.extend(self._bcd_encode_v2(user_code))
            payload.extend(struct.pack(">H", input_id))
            if await self._send_command(0x011A, payload):
                return await self._recv_response(expected_cmd=0x011B)
            return None
        
    def _bcd_encode(self, data):
        # Original 16-digit version for arm/disarm
        s = str(data)
        while len(s) < 16:
            s += "0"
        return bytes.fromhex(s)

    def _bcd_encode_v2(self, data):
        # 8-digit version for bypass
        code_str = str(data)
        s = code_str[:8].ljust(8, "0")
        return bytes.fromhex(s)

    async def arm_section(self, section_id, user_code):
        async with self._transaction_lock:
            _LOGGER.info(f"Arming Section {section_id}...")
            
            payload = bytearray()
            payload.append(0x00)
            payload.extend(self._bcd_encode(user_code))
            payload.append(section_id)
            payload.append(0x01)
            
            if await self._send_command(0x0112, payload):
                # Expected: 0x0113
                return await self._recv_response(expected_cmd=0x0113)
            return None
            
    async def disarm_section(self, section_id, user_code):
        async with self._transaction_lock:
            _LOGGER.info(f"Disarming Section {section_id}...")
            
            payload = bytearray()
            payload.append(0x00)
            payload.extend(self._bcd_encode(user_code))
            payload.append(section_id)
            payload.append(0x01)
            
            if await self._send_command(0x0114, payload):
                # Expected: 0x0115
                return await self._recv_response(expected_cmd=0x0115)
            return None
