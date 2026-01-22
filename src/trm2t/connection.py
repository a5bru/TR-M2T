"""
Connection module for establishing and managing TCP/NTRIP connections.

This module provides functionality to create TCP socket connections to NTRIP
casters and handle the NTRIP handshake protocol for data streaming.
"""

import base64
import io
import selectors
import select
import socket
import time
import sys
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from .db import update_mountpoint
from . import config
from .metrics import STREAM_STATUS

logger = logging.getLogger(__name__)

PRE_RTCM = b"\xd3"


def _calculate_crc24(data: bytes) -> bytes:
    """
    Calculate CRC24 for RTCM message validation.

    Args:
        data: The data bytes to calculate CRC for (excluding CRC itself).

    Returns:
        3-byte CRC value as bytes.
    """
    CRC24_POLY = 0x1864CFB
    crc = 0

    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= CRC24_POLY

    return bytes([(crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF])


class RTCMParser:
    """Streaming RTCM message parser that maintains state across buffer updates."""

    def __init__(self, validate_crc: bool = False):
        """
        Initialize the RTCM parser.

        Args:
            validate_crc: Whether to validate CRC24 of messages (default: False).
        """
        self.validate_crc = validate_crc
        self.last_error = None

    def parse(self, buffer: io.BytesIO) -> Optional[tuple]:
        """
        Parse next complete RTCM message from buffer.

        This method reads from the current buffer position and extracts one complete
        RTCM message if available. Returns None if not enough data for a complete message.

        Args:
            buffer: The BytesIO buffer containing RTCM data.

        Returns:
            Tuple of (message_id, raw_message) if a complete message is found, None otherwise.
            On error, returns (None, None).
        """
        start_pos = buffer.tell()

        try:
            # Look for RTCM preamble (0xd3)
            preamble = buffer.read(1)
            if not preamble:
                # No data available
                buffer.seek(start_pos)
                return None

            if preamble != PRE_RTCM:
                # Not at a valid RTCM boundary, search for next preamble
                current_pos = buffer.tell()
                remaining = buffer.read()
                prefix_idx = remaining.find(PRE_RTCM)

                if prefix_idx == -1:
                    # No preamble found in remaining data
                    buffer.seek(start_pos)
                    return None

                # Found preamble, seek to it
                buffer.seek(current_pos + prefix_idx)
                preamble = buffer.read(1)
                if not preamble:
                    buffer.seek(start_pos)
                    return None

            # Read length field (2 bytes)
            length_bytes = buffer.read(2)
            if len(length_bytes) < 2:
                # Not enough data for length field
                buffer.seek(start_pos)
                return None

            # Extract message length: skip first 6 reserved bits, use next 10 bits
            # length = ((length_bytes[0] & 0x3F) << 4) | ((length_bytes[1] & 0xF0) >> 4)
            length = ((length_bytes[0] & 0b00000011) << 8) + length_bytes[1]

            # Read message data
            message_data = buffer.read(length)
            if len(message_data) < length:
                # Not enough data for complete message
                buffer.seek(start_pos)
                return None

            # Read CRC (3 bytes)
            crc_bytes = buffer.read(3)
            if len(crc_bytes) < 3:
                # Not enough data for CRC
                buffer.seek(start_pos)
                return None

            # Construct full message
            full_message = PRE_RTCM + length_bytes + message_data + crc_bytes

            # Validate CRC if enabled
            if self.validate_crc:
                expected_crc = _calculate_crc24(PRE_RTCM + length_bytes + message_data)
                if expected_crc != crc_bytes:
                    self.last_error = (
                        f"CRC mismatch: expected {expected_crc.hex()}, got {crc_bytes.hex()}"
                    )
                    # Skip this message and continue
                    return self.parse(buffer)

            # Extract message ID (first 12 bits of message_data)
            if len(message_data) >= 2:
                message_id = ((message_data[0] << 8) | message_data[1]) >> 4
            else:
                message_id = 0

            return (message_id, full_message)

        except Exception as e:
            self.last_error = str(e)
            buffer.seek(start_pos)
            return None

    def parse_all(self, buffer: io.BytesIO) -> list:
        """
        Parse all available complete RTCM messages from buffer.

        Args:
            buffer: The BytesIO buffer containing RTCM data.

        Returns:
            List of (message_id, raw_message) tuples.
        """
        messages = []
        buffer.seek(0)

        while True:
            result = self.parse(buffer)
            if result is None:
                break
            messages.append(result)

        return messages


class InactiveMountpoint:
    """Represents an inactive mountpoint with retry tracking."""

    def __init__(self) -> None:
        """
        Initialize an InactiveMountpoint.

        Returns:
            None
        """
        self.count: int = 0
        self.last_attempt: float = time.time()
        self.pending: bool = False  # True while a connection attempt is in progress


class DataConnection:
    """Represents an active data connection to an NTRIP source."""

    def __init__(
        self,
        idx: int,
        url: str,
        socket: socket.socket,
        name: str = "",
        timeout: int = 15,
        active: bool = True,
    ) -> None:
        """
        Initialize a DataConnection.

        Args:
            idx: The mountpoint ID.
            url: The connection URL.
            socket: The socket object for this connection.
            name: The mountpoint name (default: "").
            timeout: The socket timeout in seconds (default: 15).
            active: Whether the connection is active (default: True).

        Returns:
            None
        """
        self.idx: int = idx
        self.url: str = url
        self.name: str = name
        self.timeout: int = timeout
        self.active: bool = active
        self.socket: socket.socket = socket
        self._buffer: io.BytesIO = io.BytesIO()
        self._rtcm_parser: RTCMParser = RTCMParser(validate_crc=True)


def create_tcp_client(url: str, timeout: int = 15) -> Optional[socket.socket]:
    """
    Create a TCP client connection to an NTRIP caster.

    Attempts to establish a connection to an NTRIP server with exponential backoff retry logic.
    For NTRIP connections, sends an HTTP GET request with Basic authentication.
    For plain TCP connections, establishes a raw socket connection.

    Args:
        url: Connection URL (ntrip://user:pass@host:port/path or tcp://host:port).
        timeout: Socket timeout in seconds (default: 15).

    Returns:
        A connected socket.socket object on success, or None if connection fails after all retries.

    Raises:
        ValueError: If the URL scheme is neither 'ntrip' nor 'tcp'.
    """
    # Parse url info
    o = urlparse(url)
    host = o.hostname
    port = o.port
    path = o.path
    auth = base64.b64encode(f"{o.username}:{o.password}".encode()).decode()

    # Create a TCP socket with reconnection attempts
    max_retries = 5
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            server_address = (host, port)
            seconds = 1.0
            client_socket.connect(server_address)

            if o.scheme.lower() == "ntrip":
                request = []
                request.append(f"GET {path} HTTP/1.0")
                request.append(f"User-Agent: {config.USER_AGENT}")
                request.append("Connection: close")
                request.append(f"Host: {host}")
                request.append(f"Authorization: Basic {auth}")
                request.append("")
                request.append("")
                request_str = "\r\n".join(request)
                client_socket.sendall(request_str.encode())
                readable, _, _ = select.select(
                    [
                        client_socket,
                    ],
                    [],
                    [],
                    seconds,
                )
                if not readable:
                    raise TimeoutError(f"E: {path}: No Response within {seconds} sec(s).")
                data = client_socket.recv(config.RECV_BUFFER_SIZE)
                # make sure request was not denied
                if data.startswith(b"HTTP"):
                    raise ConnectionError(f"E: {path}: Response Error {data[:20].decode()}..")
                if b"SOURCETABLE" in data:
                    raise ConnectionError(f"E: {path}: No Data available")
                if not data.startswith(b"ICY 200 OK"):
                    raise ConnectionError(f"E: {path}: No Ntrip Response")
            elif o.scheme.lower() == "tcp":
                # simple TCP connection, no handshake
                pass
            else:
                raise ValueError(f"E: {path}: Unsupported scheme {o.scheme}")
            return client_socket
        except Exception as e:
            logger.error(
                f"TCP connection error (attempt {attempt+1}/{max_retries}): {e}",
            )
            try:
                client_socket.close()
            except Exception:
                pass
            # Exponential backoff per attempt
            time.sleep(retry_delay * (2**attempt))
    logger.error(
        f"Failed to connect to TCP server after {max_retries} attempts ({path}).",
    )
    return None


def creation_thread(
    id: int,
    connection_string: str,
    name: str,
    timeout: int = 15,
    selector: Optional[selectors.BaseSelector] = None,
    connections: Optional[Dict[int, DataConnection]] = None,
    inactive: Optional[Dict[str, InactiveMountpoint]] = None,
) -> None:
    """
    Establish a connection to an NTRIP source and register it with the selector.

    Attempts to create a TCP/NTRIP connection and register it for event monitoring.
    Updates metrics and tracks inactive connections with exponential backoff.

    Args:
        id: The mountpoint ID.
        connection_string: The connection URL (ntrip://user:pass@host:port/path).
        name: The mountpoint name.
        timeout: Socket timeout in seconds (default: 15).
        selector: Optional selector.BaseSelector for registering the socket.
        connections: Optional dictionary to store active connections.
        inactive: Optional dictionary to track inactive mountpoints.

    Returns:
        None
    """
    # o = urlparse(connection_string)
    logger.info(f"{name}: Opening connection (fd={id})")
    conn = create_tcp_client(connection_string, timeout=timeout)
    if conn is not None:
        fd = conn.fileno()
        selector.register(conn, selectors.EVENT_READ)
        connections[fd] = DataConnection(
            idx=id, url=connection_string, name=name, timeout=timeout, socket=conn, active=True
        )
        try:
            STREAM_STATUS.labels(mountpoint=name).set(1)
        except Exception:
            pass
        if name in inactive:
            inactive.pop(name)
    else:
        if name not in inactive:
            inactive[name] = InactiveMountpoint()
        else:
            # Update existing entry
            inactive[name].count += 1
            inactive[name].last_attempt = time.time()

        try:
            STREAM_STATUS.labels(mountpoint=name).set(0)
        except Exception:
            pass

        attempt_count = (
            inactive[name].count if isinstance(inactive[name], InactiveMountpoint) else 0
        )
        if attempt_count > config.HUB_MAX_INACTIVE_COUNT:
            # TODO disable mountpoint
            update_mountpoint(id, active=False)
        else:
            logger.info(
                f"{name}, attempt count: {attempt_count}, last attempt: {inactive[name].last_attempt}"
            )

    # Clear pending flag once attempt completes
    if inactive is not None and name in inactive:
        inactive[name].pending = False
