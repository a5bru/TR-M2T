import base64
import io
import selectors
import select
import socket
import time
import sys
import logging
from urllib.parse import urlparse

from .db import update_mountpoint
from . import config
from .metrics import STREAM_STATUS

logger = logging.getLogger(__name__)


class DataConnection:
    def __init__(self, idx: int, url: str, socket: socket.socket, active: bool = True):
        self.idx = idx
        self.url = url
        self.active = active
        self.socket = socket
        self._buffer = io.BytesIO()


def create_tcp_client(url: str, timeout: int = 15):
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


def creation_thread(id: int, connection_string: str, timeout: int = 15, selector=None, connections=None, inactive=None):
    o = urlparse(connection_string)
    logger.info(f"I: {o.path}: Opening connection (fd={id})")
    conn = create_tcp_client(connection_string, timeout=timeout)
    if conn is not None:
        fd = conn.fileno()
        selector.register(conn, selectors.EVENT_READ)
        connections[fd] = DataConnection(
            idx=id, url=connection_string, socket=conn, active=True
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
