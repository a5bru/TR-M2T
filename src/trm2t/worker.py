"""
Worker module for processing NTRIP data and publishing to MQTT.

This module defines worker threads that receive NTRIP stream data from the hub,
parse it (optionally), and publish it to MQTT topics using background threads.
"""

import io
import queue
import random
import string
import threading
import time
import traceback
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Callable
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import setproctitle
import zmq
from .metrics import STREAM_STATUS, BYTES_TRANSFERRED

from . import config
from .connection import DataConnection, RTCMParser

logger = logging.getLogger(__name__)

PRE_RTCM = b"\xd3"


def generate_random_string(length: int) -> str:
    """
    Generate a random alphanumeric string.

    Args:
        length: The desired length of the random string.

    Returns:
        A random string of the specified length containing letters and digits.
    """
    characters = string.ascii_letters + string.digits
    random_string = "".join(random.choice(characters) for _ in range(length))
    return random_string


def worker(
    name: str,
    w_id: int,
    w_pre: str,
    url: str,
    run_event: threading.Event,
    context: zmq.Context,
    connections: Dict[int, DataConnection],
) -> None:
    """
    Worker thread that processes NTRIP streams and publishes to MQTT.

    Connects to an MQTT broker, receives raw NTRIP data via ZMQ, optionally parses
    it using a background thread, and publishes it to configured MQTT topics.

    Args:
        name: Thread name for logging and identification.
        w_id: Worker ID for creating unique client identifiers.
        url: MQTT broker URL (mqtt://user:pass@host:port).
        run_event: Threading event to signal shutdown.
        context: ZMQ context for socket communication.
        connections: Dictionary of active connections indexed by file descriptor.

    Returns:
        None
    """
    setproctitle.setproctitle(name)
    logger.info(f"Thread {name}")

    receiver: zmq.Socket = context.socket(zmq.PULL)
    receiver.setsockopt(zmq.RCVHWM, config.ZMQ_HWM)  # High water mark for receive buffer
    receiver.setsockopt(zmq.RCVTIMEO, 10)  # 10ms timeout for recv - low-latency
    receiver.connect(f"tcp://localhost:{config.ZMQ_PULL_PORT}")

    poller = zmq.Poller()
    poller.register(receiver, zmq.POLLIN)

    o = urlparse(url)

    # Initialize MQTT client pool with robust reconnect
    mqtt_should_stop: threading.Event = threading.Event()
    mqtt_clients: list[tuple[mqtt.Client, threading.Event]] = []
    mqtt_rr_lock = threading.Lock()
    mqtt_rr_index = 0
    mqtt_pool_size = max(1, getattr(config, "MQTT_CLIENT_POOL_SIZE", 2))

    def next_mqtt_client() -> tuple[Optional[mqtt.Client], Optional[threading.Event]]:
        """Round-robin selection of MQTT client from the pool."""
        nonlocal mqtt_rr_index
        if not mqtt_clients:
            return None, None
        with mqtt_rr_lock:
            client, ev = mqtt_clients[mqtt_rr_index % len(mqtt_clients)]
            mqtt_rr_index += 1
            return client, ev

    def make_callbacks(client_id: str, connected_event: threading.Event):
        def on_connect(
            client: mqtt.Client,
            userdata: object,
            flags: Dict,
            rc: int,
            properties: Optional[object] = None,
        ) -> None:
            if rc == 0:
                logger.info(f"MQTT client {client_id} connected.")
                connected_event.set()
            else:
                logger.error(f"MQTT client {client_id} failed to connect, rc={rc}")
                connected_event.clear()

        def on_disconnect(
            client: mqtt.Client,
            userdata: object,
            rc: int,
            properties: Optional[object] = None,
            reason_code: Optional[int] = None,
        ) -> None:
            logger.warning(f"MQTT client {client_id} disconnected (rc={rc})")
            connected_event.clear()
            if not mqtt_should_stop.is_set():
                while not mqtt_should_stop.is_set():
                    try:
                        logger.info(f"MQTT client {client_id} attempting reconnect...")
                        client.reconnect()
                        return
                    except Exception as e:
                        logger.error(f"MQTT reconnect failed for {client_id}: {e}")
                        time.sleep(2)

        return on_connect, on_disconnect

    for idx in range(mqtt_pool_size):
        client_id = f"n2m-{w_id:02d}-{w_pre}-{idx}"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if o.username and o.password:
            client.username_pw_set(o.username, o.password)

        connected_evt: threading.Event = threading.Event()
        cb_connect, cb_disconnect = make_callbacks(client_id, connected_evt)
        client.on_connect = cb_connect
        client.on_disconnect = cb_disconnect

        # Adjust MQTT internal queues if configured
        if hasattr(client, "max_queued_messages_set"):
            max_q = getattr(config, "MQTT_MAX_QUEUED_MESSAGES", 0)
            try:
                client.max_queued_messages_set(max_q)
            except Exception:
                pass
        if hasattr(client, "max_inflight_messages_set"):
            max_inflight = getattr(config, "MQTT_MAX_INFLIGHT", 20)
            try:
                client.max_inflight_messages_set(max_inflight)
            except Exception:
                pass

        # Connect with retry
        for attempt in range(5):
            try:
                client.connect(o.hostname, o.port)
                break
            except Exception as e:
                logger.error(
                    f"MQTT initial connect failed for {client_id} (attempt {attempt+1}/5): {e}"
                )
                time.sleep(2)
        client.loop_start()
        mqtt_clients.append((client, connected_evt))

    # Wait briefly for any client to connect
    connected_any = False
    for _ in range(10):
        if any(evt.is_set() for _, evt in mqtt_clients):
            connected_any = True
            break
        time.sleep(1)
    if not connected_any:
        logger.warning(
            f"No MQTT clients connected after 10s (pool size={mqtt_pool_size}), continuing anyway."
        )
    else:
        logger.info(f"Started MQTT client pool with {mqtt_pool_size} clients")

    # Background parsing thread pool if PARSE_RAW is enabled
    parse_executor: Optional[ThreadPoolExecutor] = None
    connection_locks: Dict[int, threading.Lock] = {}

    def parse_task(fd: int, conn_obj: DataConnection, topic: str, ts: float, data: bytes) -> None:
        """Task function for parsing RTCM messages in the thread pool."""
        if conn_obj is None or fd not in connections:
            return
        tsi = time.time()
        dts = tsi - ts
        if dts > config.MESSAGE_AGE:
            logger.info(f"Message too old {topic}")
            return

        lock = connection_locks.setdefault(fd, threading.Lock())

        try:
            with lock:
                conn_obj._buffer.seek(0, io.SEEK_END)
                conn_obj._buffer.write(data)
                conn_obj._buffer.seek(0)

                messages_parsed = 0
                while True:
                    result = conn_obj._rtcm_parser.parse(conn_obj._buffer)
                    if result is None:
                        break

                    message_id, raw_message = result
                    topic_m = f"{topic}/{message_id}"
                    logger.debug(f"Topic: {topic_m}, Data: {len(raw_message)} bytes")

                    client, client_evt = next_mqtt_client()
                    if client and client_evt and client_evt.is_set():
                        client.publish(topic_m, raw_message, qos=0)
                    messages_parsed += 1

                buffer_size = len(conn_obj._buffer.getvalue())
                if buffer_size > 262144:
                    unprocessed_data = conn_obj._buffer.read()
                    logger.debug(
                        f"{conn_obj.name}: Parser compacting buffer from {buffer_size} to {len(unprocessed_data)} bytes."
                    )
                    conn_obj._buffer = io.BytesIO(unprocessed_data)

        except Exception as e:
            logger.error(f"Parsing thread error for fd={fd}: {e}")

    if config.PARSE_RAW:
        # Create thread pool with configurable size (default 4 threads per worker)
        pool_size = getattr(config, "PARSE_POOL_SIZE", 4)
        parse_executor = ThreadPoolExecutor(
            max_workers=pool_size, thread_name_prefix=f"parse-{w_id:02d}"
        )
        logger.info(f"Worker {name} started parsing pool with {pool_size} threads")

    # Main receive loop
    while not run_event.is_set():
        try:
            # Poll with low latency timeout
            socks = dict(poller.poll(timeout=10))  # 10ms timeout

            if receiver not in socks:
                continue

            fd, data = receiver.recv_pyobj(flags=zmq.NOBLOCK)
        except zmq.Again:
            continue
        except Exception as e:
            logger.error(f"ZMQ receive error: {e}")
            continue

        if fd not in connections:
            continue

        try:
            conn_obj = connections.get(fd)
            if conn_obj is None:
                continue

            logger.debug(f"{conn_obj.name} Received {len(data)} bytes of data")

            p2 = conn_obj.name
            topic = f"{config.MQTT_TOPIC_PREFIX}/{p2}/rtcm"
            topic_raw = f"{config.MQTT_TOPIC_PREFIX}/{p2}/raw"

            if not config.PARSE_RAW:
                # Raw mode: publish immediately, no parsing overhead
                client, client_evt = next_mqtt_client()
                if client and client_evt and client_evt.is_set():
                    if "AMST" in topic:
                        logger.info(f"send message {topic}")
                    client.publish(topic_raw, data, qos=0)
            else:
                # Parse mode: publish raw immediately, submit parsing to thread pool
                client, client_evt = next_mqtt_client()
                if client and client_evt and client_evt.is_set():
                    client.publish(topic_raw, data, qos=0)

                # Submit parsing task to thread pool (non-blocking)
                if parse_executor is not None:
                    ts = time.time()
                    parse_executor.submit(parse_task, fd, conn_obj, topic, ts, data)

        except Exception as e:
            logger.error(traceback.format_exc())

    # Cleanup
    mqtt_should_stop.set()
    if parse_executor is not None:
        logger.info(f"Worker {name} shutting down parsing pool...")
        parse_executor.shutdown(wait=True, cancel_futures=False)

    for client, _evt in mqtt_clients:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
