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
import socket
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
        # Captures SECTION_ARMED_STATE_CHANGED (0x0119) events from the panel
        # Format: {section_number: armed_state}
        self.section_state_events: Dict[int, int] = {}
        
    async def connect(self) -> bool:
        """Establish connection to the panel and perform handshake."""
        async with self._lock:
            if self._connected and self.writer:
                try:
                    if self.writer.is_closing():
                        raise ConnectionResetError
                    return True
                except Exception:
                    self._connected = False

            # Try connecting, with one retry if panel denies (stale slot)
            for attempt in range(2):
                _LOGGER.info(f"Connecting to {self.ip}:{self.port}... (attempt {attempt + 1})")
                try:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(self.ip, self.port), timeout=5
                    )

                    # Enable TCP keepalive to detect dead connections
                    sock = self.writer.get_extra_info('socket')
                    if sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        try:
                            # Linux (where HA runs)
                            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                        except (AttributeError, OSError):
                            try:
                                # Windows fallback
                                sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60000, 10000))
                            except (AttributeError, OSError):
                                pass  # Basic keepalive already enabled
                        _LOGGER.debug("TCP keepalive enabled (60s idle, 10s interval)")

                    # Handshake: Send 0x0001, accept any response
                    if await self._send_command(0x0001):
                        resp = await self._recv_response()  # Accept any cmd
                        if resp:
                            cmd = resp.get('command', 0)
                            if cmd == 0x0002:
                                _LOGGER.info("Connected and Authenticated!")
                                self._connected = True
                                return True
                            elif cmd == 0x0003:
                                _LOGGER.warning("Connection DENIED by panel (slot busy). Retrying in 3s...")
                                await self._close_socket()
                                await asyncio.sleep(3)
                                continue
                            else:
                                _LOGGER.error(f"Unexpected handshake response: 0x{cmd:04x}")

                    await self._close_socket()
                except Exception as e:
                    _LOGGER.error(f"Connection failed: {e}")
                    await self._close_socket()

            return False

    async def disconnect(self):
        """Cleanly disconnect with NORMAL_DISCONNECT."""
        async with self._lock:
            # Send graceful disconnect so panel frees the connection slot
            if self._connected and self.writer:
                try:
                    await self._send_command(0x0014)  # NORMAL_DISCONNECT
                    await asyncio.sleep(0.2)  # Brief pause for panel to process
                except Exception:
                    pass
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
                
                # Log ALL received commands for diagnostics
                expected_str = f"0x{expected_cmd:04x}" if expected_cmd is not None else "any"
                _LOGGER.warning(f"RECV cmd=0x{cmd_id:04x} data_len={data_len} data={data.hex() if data else 'empty'} (expecting {expected_str})")
                
                if not expected_cmd or cmd_id == expected_cmd:
                    return {'command': cmd_id, 'data': data}
                
                # Capture section state change events (e.g. physical keypad arm/disarm)
                if cmd_id == 0x0119 and len(data) >= 2:
                    section_num = data[0]
                    section_state = data[1]
                    self.section_state_events[section_num] = section_state
                    _LOGGER.warning(f"EVENT CAPTURED: Section state change (0x0119): section={section_num} state={section_state}")
                elif cmd_id == 0x0102:
                    self._process_event_0102(data)
                
                _LOGGER.warning(f"Skipping unexpected cmd 0x{cmd_id:04x} (waiting for 0x{expected_cmd:04x})")
                continue
                
            except (asyncio.TimeoutError, ConnectionResetError, asyncio.IncompleteReadError) as e:
                _LOGGER.error(f"Receive Error: {e}")
                await self._close_socket()
                return None
            except Exception as e:
                _LOGGER.exception(f"Unexpected Receive Error: {e}")
                await self._close_socket()
                return None
        
        return None

    def _process_event_0102(self, data: bytes):
        """Parse 0x0102 event log (text-based state changes)."""
        try:
            if len(data) < 12:
                return

            # Byte 1 seems to be Section ID based on testing (0x02 for section 2)
            section_num = data[1] 
            
            # Text starts at offset 10 based on sample data
            # 00 02 00 1c 1a 02 12 0b 12 09 [Text...]
            text_data = data[10:]
            try:
                # Use latin-1 to avoid decode errors on binary/garbage
                text = text_data.decode("latin-1", errors="ignore")
            except:
                return

            # Check keywords
            new_state = None
            if "INSCHAKELEN" in text:
                new_state = 1 # Armed Away
            elif "UITSCHAKELEN" in text:
                new_state = 2 # Disarmed
            
            if new_state is not None:
                self.section_state_events[section_num] = new_state
                _LOGGER.warning(f"EVENT 0x0102 PARSED: section={section_num} state={new_state} text='{text.strip()}'")

        except Exception as e:
            _LOGGER.error(f"Error parsing 0x0102 event: {e}")

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

    async def drain_events(self) -> int:
        """Non-blocking read of any buffered packets from the socket.
        
        Captures events (like 0x0119 or 0x0102) that arrived between polls.
        Returns the number of events captured.
        """
        if not self.reader or not self._connected:
            return 0
        
        events_found = 0
        async with self._transaction_lock:
            while True:
                try:
                    # Non-blocking check: is there data waiting?
                    # Use a very short timeout to check for buffered data
                    header_bytes = await asyncio.wait_for(
                        self.reader.readexactly(14), timeout=0.1
                    )
                    header = bytearray(header_bytes)
                    length = struct.unpack(">H", header[12:14])[0]
                    
                    if length < 16 or length > 4096:
                        _LOGGER.error(f"drain_events: Invalid packet length: {length}")
                        break
                    
                    remaining_bytes = length - 14
                    body = await asyncio.wait_for(
                        self.reader.readexactly(remaining_bytes), timeout=1
                    )
                    
                    payload_enc = body[:-2]
                    payload_dec = self._decrypt(payload_enc, header)
                    
                    cmd_id = struct.unpack(">H", payload_dec[:2])[0]
                    data_len = struct.unpack(">H", payload_dec[2:4])[0]
                    data = payload_dec[4:4+data_len]
                    
                    self.session_id = struct.unpack(">H", header[:2])[0]
                    self.rx_seq = struct.unpack(">I", header[2:6])[0]
                    
                    _LOGGER.warning(f"DRAIN: Received cmd=0x{cmd_id:04x} data={data.hex() if data else 'empty'}")
                    
                    # Capture section state change events
                    if cmd_id == 0x0119 and len(data) >= 2:
                        section_num = data[0]
                        section_state = data[1]
                        self.section_state_events[section_num] = section_state
                        _LOGGER.warning(f"DRAIN EVENT (0x0119): Section state change: section={section_num} state={section_state}")
                        events_found += 1
                    elif cmd_id == 0x0102:
                        self._process_event_0102(data)
                        events_found += 1
                    
                except asyncio.TimeoutError:
                    # No more buffered data — normal exit
                    break
                except Exception as e:
                    _LOGGER.warning(f"drain_events error: {e}")
                    break
        
        return events_found

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
