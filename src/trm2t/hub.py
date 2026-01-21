"""
Hub module for managing NTRIP to MQTT connections.

This module implements the central hub that manages multiple NTRIP connections,
worker threads for message distribution, and event handling for stream management.
"""

import queue
import socket
import selectors
import time
import threading
import logging
from typing import Dict, Optional, Any
from urllib.parse import urlparse
import zmq
import setproctitle
from concurrent.futures import ThreadPoolExecutor

from . import config
from .worker import worker, generate_random_string
from .metrics import STREAM_STATUS, BYTES_TRANSFERRED
from prometheus_client import start_http_server
from .connection import creation_thread, DataConnection
from .db import fetch_active_mountpoints

logger = logging.getLogger(__name__)

context: zmq.Context = zmq.Context()
selector: selectors.DefaultSelector = selectors.DefaultSelector()
connections: Dict[int, DataConnection] = {}
inactive: Dict[str, Any] = {}

run_event: threading.Event = threading.Event()

enable_queue: queue.Queue = queue.Queue()


def check_mountpoints(name: str, sock: socket.socket) -> None:
    """
    Periodically check for active mountpoints and manage connections.

    Monitors the database for active mountpoints, creates new connections,
    closes inactive ones, and tracks offline streams with exponential backoff.

    Args:
        name: Thread name for logging.
        sock: Socket for signaling connection changes to the event handler.

    Returns:
        None
    """

    setproctitle.setproctitle(name)
    logger.info(f"Thread {name}")

    while not run_event.is_set():

        logger.info("Check for active mountpoints")
        active_mountpoints = fetch_active_mountpoints()
        active_ids = set(mp[0] for mp in active_mountpoints)
        mount_map = {mp[0]: urlparse(mp[1]).path.lstrip("/") for mp in active_mountpoints}
        found_inactive = False

        # shut down active stream
        for fd in list(connections.keys()):
            if connections[fd].idx not in active_ids:
                enable_queue.put_nowait(int(fd))
                o = urlparse(connections[fd].url)
                logger.info(f"I: {o.path}: Closing connection")
                found_inactive = True

        if found_inactive:
            sock.sendall(b"1")

        # active stream
        active_streams = []

        for fd in list(connections.keys()):
            active_streams.append(connections[fd].idx)

        # mark not-connected active mountpoints as offline
        for mp_id, mount in mount_map.items():
            if mp_id not in active_streams:
                try:
                    STREAM_STATUS.labels(mountpoint=mount).set(0)
                except Exception:
                    pass

        # Parallelize mountpoint creation with multiple loader threads
        # Apply exponential backoff for failed connections
        to_create = []
        current_time = time.time()
        for id, connection_string, name, timeout in active_mountpoints:
            if id not in active_streams:
                o = urlparse(connection_string)
                path = o.path
                # Check if we should retry based on exponential backoff
                if path not in inactive:
                    # First attempt
                    to_create.append((id, connection_string, name, timeout))
                else:
                    # Exponential backoff: wait 2^attempt seconds
                    attempt_count = inactive[path] if isinstance(inactive[path], int) else inactive[path].get('count', 0)
                    last_attempt = inactive[path].get('last_attempt', 0) if isinstance(inactive[path], dict) else current_time
                    backoff_time = 2 ** min(attempt_count, 8)  # Cap at 2^8 = 256 seconds
                    if current_time - last_attempt >= backoff_time:
                        to_create.append((id, connection_string, name, timeout))
        
        if to_create:

            def loader(args):
                creation_thread(*args, selector=selector, connections=connections, inactive=inactive)

            with ThreadPoolExecutor(max_workers=config.HUB_CREATION_LOADERS) as executor:
                executor.map(loader, to_create)

        time.sleep(10)


def handle_events(name: str, sock: socket.socket) -> None:
    """
    Handle incoming data from NTRIP connections and manage stream lifecycle.

    Listens for data on registered connections, forwards it to worker threads via ZMQ,
    and handles connection cleanup when streams are inactive.

    Args:
        name: Thread name for logging.
        sock: Socket for receiving connection management signals.

    Returns:
        None
    """

    setproctitle.setproctitle(name)
    logger.info(f"Thread {name}")

    sender: zmq.Socket = context.socket(zmq.PUSH)
    sender.bind(f"tcp://*:{config.ZMQ_PULL_PORT}")
    selector.register(sock, selectors.EVENT_READ)

    while not run_event.is_set():

        events = selector.select(timeout=2.0)

        for key, _ in events:
            conn = key.fileobj
            data = conn.recv(config.RECV_BUFFER_SIZE)

            if conn == sock:
                # remove a connection
                conn.recv(10)
                while not enable_queue.empty():
                    fd = int(enable_queue.get())
                    enable_queue.task_done()
                    # fd = int(fd_b)
                    if fd in connections:
                        selector.unregister(connections[fd].socket)
                        connections[fd].active = False
                        try:
                            o = urlparse(connections[fd].url)
                            STREAM_STATUS.labels(mountpoint=o.path[1:]).set(0)
                        except Exception:
                            pass
                        connections[fd].socket.close()
                        del connections[fd]

            else:
                fd = conn.fileno()
                if data:
                    try:
                        o = urlparse(connections[fd].url)
                        mount = o.path[1:]
                        STREAM_STATUS.labels(mountpoint=mount).set(1)
                        BYTES_TRANSFERRED.labels(mountpoint=mount).inc(len(data))
                    except Exception:
                        pass
                    sender.send_pyobj((fd, data))
                else:
                    selector.unregister(conn)
                    conn.close()
                    if fd in connections:
                        connections[fd].active = False
                        try:
                            o = urlparse(connections[fd].url)
                            STREAM_STATUS.labels(mountpoint=o.path[1:]).set(0)
                        except Exception:
                            pass
                        del connections[fd]


def main(name: str) -> None:
    """
    Initialize and run the NTRIP to MQTT hub.

    Starts the Prometheus metrics server, initializes worker threads for MQTT publishing,
    and starts the connection checker and event handler threads. Waits for termination signal.

    Args:
        name: Thread name for logging.

    Returns:
        None
    """

    # Start Prometheus metrics server
    start_http_server(config.PROM_PORT)
    logger.info(f"Prometheus endpoint started on :{config.PROM_PORT}")

    sock1, sock2 = socket.socketpair()

    # Check MQTT connection
    while not run_event.is_set():
        try:
            with socket.create_connection((config.MQTT_HOST, config.MQTT_PORT), timeout=5):
                logger.info(f"Successfully connected to MQTT broker at {config.MQTT_HOST}:{config.MQTT_PORT}")
                break
        except OSError as e:
            logger.error(f"Failed to connect to MQTT broker at {config.MQTT_HOST}:{config.MQTT_PORT}: {e}")
            logger.info("Retrying in 5 seconds...")
            time.sleep(5)

    # start worker threads
    mqtt_url = f"mqtt://{config.MQTT_USER}:{config.MQTT_PSWD}@{config.MQTT_HOST}:{config.MQTT_PORT}"
    logger.info(f"MQTT_URL: {mqtt_url}")
    worker_prefix: str = generate_random_string(8)
    for i in range(config.WORKERS):
        t = threading.Thread(
            target=worker,
            args=(
                f"HUB/WRK/{i:02d}",
                i,
                worker_prefix,
                mqtt_url,
                run_event,
                context,
                connections,
            ),
        )
        t.daemon = True
        t.start()
    time.sleep(3)

    # start checker thread
    db_thread = threading.Thread(
        target=check_mountpoints,
        args=(
            "HUB/CHK",
            sock1,
        ),
    )
    db_thread.daemon = True
    db_thread.start()

    # start selector
    ev_thread = threading.Thread(
        target=handle_events,
        args=(
            "HUB/EVE",
            sock2,
        ),
    )
    ev_thread.daemon = True
    ev_thread.start()

    setproctitle.setproctitle(name)
    logger.info(f"Thread {name}")

    while not run_event.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main("HUB/MAIN")
