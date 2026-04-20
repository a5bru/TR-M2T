"""
TCP relay server manager.

Starts one TCP server per active mountpoint and pushes incoming NTRIP bytes to
any connected TCP clients. All servers and clients are handled from a single
selector-driven thread to avoid spawning per-connection threads.
"""

import logging
import queue
import selectors
import socket
import threading
import setproctitle

from typing import Dict, Optional, Set

from . import config

logger = logging.getLogger(__name__)


class _ServerState:
    """Internal container for a mountpoint TCP server."""

    def __init__(self, name: str, port: int, server_socket: socket.socket) -> None:
        self.name = name
        self.port = port
        self.server_socket = server_socket
        self.clients: Set[socket.socket] = set()


class TcpServerManager:
    """Manage per-mountpoint TCP servers in a single selector thread."""

    def __init__(
        self,
        run_event: threading.Event,
        *,
        bind_host: str = "0.0.0.0",
        base_port: int = 24000,
        backlog: int = 8,
        queue_size: int = 5000,
        enabled: bool = True,
    ) -> None:
        self._run_event = run_event
        self._bind_host = bind_host
        self._base_port = base_port
        self._backlog = backlog
        self._enabled = enabled
        self._selector: selectors.BaseSelector = selectors.DefaultSelector()
        self._servers: Dict[str, _ServerState] = {}
        self._data_queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._command_queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Launch the selector thread if relay is enabled."""
        if not self._enabled:
            logger.info("TCP relay disabled via configuration")
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="TCP-Relay", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request shutdown and wait briefly for the thread to exit."""
        if not self._enabled:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._cleanup_all()

    def ensure_server(self, conn_obj, port: Optional[int] = None) -> Optional[int]:
        """Create a TCP server for the given connection if not already running."""
        if not self._enabled or conn_obj is None:
            return None

        name = getattr(conn_obj, "name", None) or str(getattr(conn_obj, "idx", ""))
        with self._lock:
            if name in self._servers:
                return self._servers[name].port

        target_port = port if port is not None else self._base_port + getattr(conn_obj, "idx", 0)
        server_socket: Optional[socket.socket] = None
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self._bind_host, target_port))
            server_socket.listen(self._backlog)
            server_socket.setblocking(False)
        except OSError as exc:
            logger.error(
                "Failed to start TCP relay for %s on %s:%s: %s",
                name,
                self._bind_host,
                target_port,
                exc,
            )
            try:
                server_socket.close()  # type: ignore[arg-type]
            except Exception:
                pass
            return None

        self._command_queue.put(("add", name, server_socket, target_port))
        return target_port

    def remove_server(self, mount_name: str) -> None:
        """Schedule teardown of a TCP server for the given mountpoint."""
        if not self._enabled:
            return
        self._command_queue.put(("remove", mount_name, None, None))

    def broadcast(self, mount_name: str, payload: bytes) -> None:
        """Queue bytes to broadcast to all TCP clients of a mountpoint."""
        if not self._enabled or not payload:
            return
        try:
            self._data_queue.put_nowait((mount_name, payload))
        except queue.Full:
            logger.warning(
                "TCP relay queue full for %s; dropping %d bytes", mount_name, len(payload)
            )

    # --- internal helpers ---

    def _run(self) -> None:
        setproctitle.setproctitle("HUB/RELAY")
        while not self._stop_event.is_set() and not self._run_event.is_set():
            self._process_commands()
            self._service_selector()
            self._flush_data()
        self._cleanup_all()

    def _process_commands(self) -> None:
        while True:
            try:
                action, mount, sock, port = self._command_queue.get_nowait()
            except queue.Empty:
                break

            if action == "add" and sock is not None and port is not None:
                state = _ServerState(mount, port, sock)
                with self._lock:
                    self._servers[mount] = state
                self._selector.register(
                    sock, selectors.EVENT_READ, {"role": "server", "mount": mount}
                )
                logger.info("TCP relay for %s listening on %s:%s", mount, self._bind_host, port)
            elif action == "remove":
                self._teardown_server(mount)

    def _service_selector(self) -> None:
        try:
            events = self._selector.select(timeout=0.01)
        except Exception:
            return

        for key, _ in events:
            role = key.data.get("role") if isinstance(key.data, dict) else None
            mount = key.data.get("mount") if isinstance(key.data, dict) else None
            if role == "server":
                self._accept_client(key.fileobj, mount)
            elif role == "client":
                self._drain_client(key.fileobj, mount)

    def _accept_client(self, server_sock: socket.socket, mount: Optional[str]) -> None:
        if mount is None:
            return
        try:
            client, addr = server_sock.accept()
            client.setblocking(False)
        except BlockingIOError:
            return
        except OSError as exc:
            logger.debug("Accept failed for %s: %s", mount, exc)
            return

        with self._lock:
            state = self._servers.get(mount)
            if state is None:
                try:
                    client.close()
                except Exception:
                    pass
                return
            state.clients.add(client)
        self._selector.register(client, selectors.EVENT_READ, {"role": "client", "mount": mount})
        logger.info("TCP client connected for %s from %s", mount, addr)

    def _drain_client(self, client: socket.socket, mount: Optional[str]) -> None:
        try:
            data = client.recv(1024)
            if data:
                return  # Ignore inbound payloads
        except BlockingIOError:
            return
        except OSError:
            pass
        self._drop_client(client, mount)

    def _flush_data(self) -> None:
        iterations = 0
        while iterations < 200:
            iterations += 1
            try:
                mount, payload = self._data_queue.get_nowait()
            except queue.Empty:
                break

            with self._lock:
                state = self._servers.get(mount)
                clients = list(state.clients) if state else []
            if not clients:
                continue

            for client in clients:
                self._send_payload(client, mount, payload)

    def _send_payload(self, client: socket.socket, mount: Optional[str], payload: bytes) -> None:
        view = memoryview(payload)
        sent_total = 0
        while sent_total < len(payload):
            try:
                sent = client.send(view[sent_total:])
                if sent == 0:
                    self._drop_client(client, mount)
                    return
                sent_total += sent
            except (BlockingIOError, InterruptedError):
                # Leave remaining bytes for the next broadcast cycle
                return
            except OSError:
                self._drop_client(client, mount)
                return

    def _drop_client(self, client: socket.socket, mount: Optional[str]) -> None:
        try:
            self._selector.unregister(client)
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
        if mount is None:
            return
        with self._lock:
            state = self._servers.get(mount)
            if state:
                state.clients.discard(client)

    def _teardown_server(self, mount: str) -> None:
        with self._lock:
            state = self._servers.pop(mount, None)
        if state is None:
            return
        try:
            self._selector.unregister(state.server_socket)
        except Exception:
            pass
        try:
            state.server_socket.close()
        except Exception:
            pass
        for client in list(state.clients):
            self._drop_client(client, mount)
        logger.info("TCP relay for %s stopped", mount)

    def _cleanup_all(self) -> None:
        with self._lock:
            mounts = list(self._servers.keys())
        for mount in mounts:
            self._teardown_server(mount)
        try:
            self._selector.close()
        except Exception:
            pass


def build_tcp_manager(run_event: threading.Event) -> TcpServerManager:
    """Factory to build a manager from configuration values."""
    return TcpServerManager(
        run_event,
        bind_host=config.TCP_RELAY_BIND,
        base_port=config.TCP_RELAY_BASE_PORT,
        backlog=config.TCP_RELAY_BACKLOG,
        queue_size=config.TCP_RELAY_QUEUE,
        enabled=config.TCP_RELAY_ENABLED,
    )
