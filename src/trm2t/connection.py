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


class DataConnection:
    """Represents an active data connection to an NTRIP source."""

    def __init__(self, idx: int, url: str, socket: socket.socket, name: str = "", timeout: int = 15, active: bool = True) -> None:
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
                request = f"GET {path} HTTP/1.0\r\n"
                request += f"User-Agent: {config.USER_AGENT}\r\n"
                request += "Connection: close\r\n"
                request += f"Host: {host}\r\n"
                request += f"Authorization: Basic {auth}\r\n"
                request += "\r\n"
                client_socket.sendall(request.encode())
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
            time.sleep(retry_delay * (2 ** attempt))
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
    inactive: Optional[Dict[str, Any]] = None,
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
    o = urlparse(connection_string)
    logger.info(f"I: {name}: Opening connection (fd={id})")
    conn = create_tcp_client(connection_string, timeout=timeout)
    if conn is not None:
        fd = conn.fileno()
        selector.register(conn, selectors.EVENT_READ)
        connections[fd] = DataConnection(
            idx=id, url=connection_string, name=name, timeout=timeout, socket=conn, active=True
        )
        try:
            STREAM_STATUS.labels(mountpoint=o.path.lstrip("/")).set(1)
        except Exception:
            pass
        if o.path in inactive:
            inactive.pop(o.path)
    else:
        if o.path not in inactive:
            inactive[o.path] = {'count': 0, 'last_attempt': time.time()}
        elif isinstance(inactive[o.path], int):
            # Migrate old format to new format
            inactive[o.path] = {'count': inactive[o.path], 'last_attempt': time.time()}
        else:
            # Update existing entry
            inactive[o.path]['count'] += 1
            inactive[o.path]['last_attempt'] = time.time()

        try:
            STREAM_STATUS.labels(mountpoint=o.path.lstrip("/")).set(0)
        except Exception:
            pass

        attempt_count = inactive[o.path]['count'] if isinstance(inactive[o.path], dict) else inactive[o.path]
        if attempt_count > config.HUB_MAX_INACTIVE_COUNT:
            # TODO disable mountpoint
            update_mountpoint(id, active=False)
        else:
            logger.info(f"{o.path}, attempt count: {attempt_count}, last attempt: {inactive[o.path]['last_attempt']}")
