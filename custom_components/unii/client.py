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
"""Unii Client for Home Assistant (Refactored v2.0)."""
import asyncio
import struct
import binascii
import logging
from typing import Optional, Dict, Any, Tuple
from Crypto.Cipher import AES
from Crypto.Util import Counter

_LOGGER = logging.getLogger(__name__)

class UniiClient:
    def __init__(self, ip: str, port: int = 6502, shared_key: Optional[str] = None):
        self.ip = ip
        self.port = port
        self.shared_key = shared_key
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.session_id = 0xFFFF
        self.tx_seq = 0
        self.rx_seq = 0
        self._connected = False
        self._lock = asyncio.Lock()
        self._transaction_lock = asyncio.Lock()
        
    async def connect(self) -> bool:
        """Establish connection to the panel and perform handshake."""
        async with self._lock:
            if self._connected and self.writer:
                try:
                    # Quick check if writer is still valid (not foolproof but helps)
                    if self.writer.is_closing():
                        raise ConnectionResetError
                    return True
                except Exception:
                    self._connected = False

            _LOGGER.info(f"Connecting to {self.ip}:{self.port}...")
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=5
                )
                
                # Handshake: Send 0x0001, Expect 0x0002
                if await self._send_command(0x0001): 
                    resp = await self._recv_response(expected_cmd=0x0002)
                    if resp:
                        _LOGGER.info("Connected and Authenticated!")
                        self._connected = True
                        return True
                        
                # Handshake failed
                await self._close_socket()
                return False
            except Exception as e:
                _LOGGER.error(f"Connection failed: {e}")
                await self._close_socket()
                return False

    async def disconnect(self):
        """Cleanly disconnect."""
        async with self._lock:
            await self._close_socket()
            _LOGGER.info("Disconnected.")

    async def _close_socket(self):
        """Internal socket cleanup."""
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

    def _encrypt(self, payload: bytearray, header: bytearray) -> bytearray:
        """Encrypt payload using AES-CTR if shared_key is set."""
        if not self.shared_key:
            return payload
            
        key_padded = self.shared_key[:16].ljust(16, " ")
        key_bytes = key_padded.encode("utf-8")
        
        # IV = First 12 bytes of Header + 00000000
        iv = header[:12] + b'\x00\x00\x00\x00'
        
        ctr = Counter.new(128, initial_value=int.from_bytes(iv, 'big'))
        cipher = AES.new(key_bytes, AES.MODE_CTR, counter=ctr)
        return bytearray(cipher.encrypt(payload))

    def _decrypt(self, payload_enc: bytes, header: bytearray) -> bytearray:
        return self._encrypt(bytearray(payload_enc), header)

    def _calculate_crc16(self, data: bytearray) -> int:
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

    async def _send_command(self, command_id: int, data: bytes = b"") -> bool:
        """Construct and send a packet."""
        if not self.writer:
            return False

        proto_id = 0x05 if self.shared_key else 0x04
        packet_type = 0x01 if command_id < 0x0008 else 0x02
        
        # Header (14 bytes)
        header = struct.pack(">HIIBB", self.session_id, self.tx_seq, self.rx_seq, proto_id, packet_type) + b'\x00\x00'
        header = bytearray(header)
        
        # Payload
        payload = bytearray(struct.pack(">HH", command_id, len(data)) + data)
        
        # Padding
        packet_len_temp = len(header) + len(payload) + 2
        pad_len = (16 - (packet_len_temp % 16)) % 16
        payload += b'\x00' * pad_len
        
        # Encrypt
        payload_enc = self._encrypt(payload, header)
        msg = header + payload_enc
        
        # Update Length in Header (Indices 12, 13)
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
            await self._close_socket()
            return False

    async def _recv_response(self, expected_cmd: Optional[int] = None, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Receive response, filtering out unexpected events (race condition fix)."""
        if not self.reader:
            return None
            
        max_retries = 10 
        start_time = asyncio.get_running_loop().time()

        for attempt in range(max_retries):
            # Check total timeout
            if asyncio.get_running_loop().time() - start_time > timeout:
                _LOGGER.warning(f"Timeout waiting for CMD 0x{expected_cmd:04x}")
                return None

            try:
                # Calculate remaining time for this read operation
                remaining_time = timeout - (asyncio.get_running_loop().time() - start_time)
                if remaining_time <= 0: return None

                # Header
                header_bytes = await asyncio.wait_for(self.reader.readexactly(14), timeout=remaining_time)
                header = bytearray(header_bytes)
                length = struct.unpack(">H", header[12:14])[0]
                
                # Check sane length
                if length < 16 or length > 4096:
                    _LOGGER.error(f"Invalid packet length: {length}")
                    return None

                remaining_bytes = length - 14
                body = await asyncio.wait_for(self.reader.readexactly(remaining_bytes), timeout=remaining_time)
                
                # Decrypt
                payload_enc = body[:-2]
                payload_dec = self._decrypt(payload_enc, header)
                
                cmd_id = struct.unpack(">H", payload_dec[:2])[0]
                data_len = struct.unpack(">H", payload_dec[2:4])[0]
                data = payload_dec[4:4+data_len]
                
                # Update Session State
                self.session_id = struct.unpack(">H", header[:2])[0]
                self.rx_seq = struct.unpack(">I", header[2:6])[0] 
                
                if not expected_cmd or cmd_id == expected_cmd:
                    return {'command': cmd_id, 'data': data}
                
                _LOGGER.debug(f"Skipping unexpected cmd 0x{cmd_id:04x} (waiting for 0x{expected_cmd:04x})")
                continue
                
            except (asyncio.TimeoutError, ConnectionResetError, asyncio.IncompleteReadError) as e:
                _LOGGER.error(f"Receive Error: {e}")
                await self._close_socket()
                return None
            except Exception as e:
                _LOGGER.exception(f"Unexpected Receive Error: {e}")
                return None
        
        return None

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """Fetch status of all sections."""
        async with self._transaction_lock:
            # Request Section Status (0x0116)
            mask = b'\xFF' * 4
            if await self._send_command(0x0116, b'\x01' + mask):
                return await self._recv_response(expected_cmd=0x0117)
            return None

    async def get_input_status(self) -> Optional[Dict[str, Any]]:
        """Fetch status of all inputs."""
        async with self._transaction_lock:
            if await self._send_command(0x0106, b'\x02'):
                return await self._recv_response(expected_cmd=0x0105)
            return None

    async def get_input_arrangement(self) -> Dict[str, Dict]:
        """Fetch input arrangement (all blocks)."""
        inputs = {}
        async with self._transaction_lock:
            for block in range(1, 101): # 1 to 100
                payload = struct.pack(">H", block)
                if not await self._send_command(0x0140, payload):
                    _LOGGER.warning(f"Failed to send arrangement request for block {block}")
                    break

                resp = await self._recv_response(expected_cmd=0x0141, timeout=3)
                if not resp or len(resp['data']) < 3:
                     _LOGGER.debug(f"Block {block} empty/invalid response, stopping.")
                     # If block return empty, usually it means end of inputs? 
                     # Wait, we decided to purge early exit logic -> BUT if 'data' is basically empty/short, 
                     # it means the panel literally has no data for this block.
                     # However, v1.6.7 said "removed early exit".
                     # If the panel returns a VALID packet with 0 inputs, we continue.
                     # If it returns NOTHING or INVALID, we stop?
                     # Let's keep scanning unless error.
                     if not resp: break
                     
                data = resp['data']
                offset = 3
                items_in_block = 0
                
                while offset + 22 <= len(data):
                    input_num = ((block - 1) * 44) + items_in_block + 1
                    
                    sensor_type = data[offset+1]
                    reaction = data[offset+2]
                    name_raw = data[offset+3:offset+19]
                    name = name_raw.decode("utf-8", errors="replace").strip()
                    
                    # Valid Input Check
                    if name and not all(c == '\x00' for c in name) and "VRIJE TEKST" not in name:
                         inputs[input_num] = {
                            "name": name,
                            "sensor_type": sensor_type,
                            "reaction": reaction
                        }
                    
                    offset += 22
                    items_in_block += 1
                
                if items_in_block > 0:
                    _LOGGER.debug(f"Block {block}: {items_in_block} records parsed.")

        _LOGGER.info(f"Input arrangement download complete: {len(inputs)} inputs found.")
        return {"inputs": inputs}

    def _bcd_encode(self, data: str) -> bytes:
        """Encode string to 8-byte BCD (Right padded)."""
        s = str(data).ljust(16, "0")[:16]
        return bytes.fromhex(s)

    async def bypass_input(self, input_id: int, user_code: str) -> Optional[Dict[str, Any]]:
        return await self._control_input(input_id, user_code, 0x0118, 0x0119)

    async def unbypass_input(self, input_id: int, user_code: str) -> Optional[Dict[str, Any]]:
        return await self._control_input(input_id, user_code, 0x011A, 0x011B)

    async def _control_input(self, input_id: int, user_code: str, cmd_req: int, cmd_resp: int) -> Optional[Dict[str, Any]]:
        async with self._transaction_lock:
            payload = bytearray([0x00]) + self._bcd_encode(user_code) + struct.pack(">H", input_id)
            if await self._send_command(cmd_req, payload):
                return await self._recv_response(expected_cmd=cmd_resp)
            return None

    async def arm_section(self, section_id: int, user_code: str) -> bool:
        """Arm a section."""
        return await self._control_section(section_id, user_code, 0x0112, 0x0113)

    async def disarm_section(self, section_id: int, user_code: str) -> bool:
        """Disarm a section."""
        return await self._control_section(section_id, user_code, 0x0114, 0x0115)

    async def _control_section(self, section_id: int, user_code: str, cmd_req: int, cmd_resp: int) -> bool:
        """Generic section control."""
        async with self._transaction_lock:
            # Payload: 0x00 + BCD Code + 1-Byte Section ID + 0x01
            # Format matches official py-unii library (UNiiArmDisarmSection.to_bytes)
            payload = bytearray([0x00]) + self._bcd_encode(user_code) + section_id.to_bytes(1, 'big') + b'\x01'
            if await self._send_command(cmd_req, payload):
                resp = await self._recv_response(expected_cmd=cmd_resp)
                return resp is not None
            return False
