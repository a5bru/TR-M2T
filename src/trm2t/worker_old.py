"""
Worker module for processing NTRIP data and publishing to MQTT.

This module defines worker threads that receive NTRIP stream data from the hub,
parse it (optionally), and publish it to MQTT topics.
"""

import io
import random
import string
import threading
import time
import traceback
import logging
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
    it using RTCMReader, and publishes it to configured MQTT topics.

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

    # Initialize MQTT Client with robust reconnect
    mqtt_client_id = f"n2m-{w_id:02d}-{w_pre}"
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id)
    if o.username and o.password:
        mqtt_client.username_pw_set(o.username, o.password)

    mqtt_connected: threading.Event = threading.Event()
    mqtt_should_stop: threading.Event = threading.Event()

    def on_connect(
        client: mqtt.Client,
        userdata: object,
        flags: Dict,
        rc: int,
        properties: Optional[object] = None,
    ) -> None:
        """Callback for MQTT connection establishment."""
        if rc == 0:
            logger.info(f"MQTT client {mqtt_client_id} connected.")
            mqtt_connected.set()
        else:
            logger.error(f"MQTT client {mqtt_client_id} failed to connect, rc={rc}")
            mqtt_connected.clear()

    def on_disconnect(
        client: mqtt.Client,
        userdata: object,
        rc: int,
        properties: Optional[object] = None,
        reason_code: Optional[int] = None,
    ) -> None:
        """Callback for MQTT disconnection."""
        logger.warning(f"MQTT client {mqtt_client_id} disconnected (rc={rc})")
        mqtt_connected.clear()
        if not mqtt_should_stop.is_set():
            # Try to reconnect in background
            while not mqtt_should_stop.is_set():
                try:
                    logger.info(f"MQTT client {mqtt_client_id} attempting reconnect...")
                    client.reconnect()
                    return
                except Exception as e:
                    logger.error(f"MQTT reconnect failed: {e}")
                    time.sleep(2)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect

    # Connect with retry
    for attempt in range(5):
        try:
            mqtt_client.connect(o.hostname, o.port)
            break
        except Exception as e:
            logger.error(f"MQTT initial connect failed (attempt {attempt+1}/5): {e}")
            time.sleep(2)
    mqtt_client.loop_start()  # Start the MQTT client loop

    # Wait for connection
    if not mqtt_connected.wait(timeout=10):
        logger.warning(
            f"MQTT client {mqtt_client_id} could not connect after 10s, continuing anyway."
        )

    logger.info(f"Started MQTT client {mqtt_client_id}")

    while not run_event.is_set():
        try:
            # Poll with low latency timeout
            socks = dict(poller.poll(timeout=10))  # 10ms timeout for low-latency processing

            if receiver not in socks:
                continue

            fd, data = receiver.recv_pyobj(flags=zmq.NOBLOCK)
        except zmq.Again:
            # No message available, continue loop
            continue
        except Exception as e:
            logger.error(f"ZMQ receive error: {e}")
            continue

        if fd not in connections:
            continue

        try:
            # The fd might be removed by hub concurrently; re-check
            conn_obj = connections.get(fd)
            if conn_obj is None:
                continue

            # Append new data to the buffer

            logger.debug(f"{conn_obj.name} Received {len(data)} bytes of data")

            # Append new data to buffer
            conn_obj._buffer.seek(0, io.SEEK_END)
            conn_obj._buffer.write(data)

            p2 = conn_obj.name
            topic = f"{config.MQTT_TOPIC_PREFIX}/{p2}/rtcm"

            if not config.PARSE_RAW:
                # Fast path: publish only the new chunk and reset buffer
                if mqtt_connected.is_set():
                    mqtt_client.publish(topic, data, qos=0)
                conn_obj._buffer = io.BytesIO()
            else:
                # Parsing path (slower)
                logger.debug(f"{conn_obj.name}: Parsing RTCM data {len(data)} bytes")
                try:
                    # Parse all available messages from buffer
                    conn_obj._buffer.seek(0)

                    while True:
                        result = conn_obj._rtcm_parser.parse(conn_obj._buffer)
                        if result is None:
                            # No more complete messages available
                            break

                        message_id, raw_message = result
                        topic_m = f"{topic}/{message_id}"
                        logger.debug(f"Topic: {topic_m}, Data: {len(raw_message)} bytes")

                        if mqtt_connected.is_set():
                            mqtt_client.publish(topic_m, raw_message, qos=0)

                    # Compact buffer if it's getting large (> 128KB)
                    current_pos = conn_obj._buffer.tell()
                    buffer_size = len(conn_obj._buffer.getvalue())

                    if buffer_size > 131072:
                        # Keep unprocessed data, discard processed
                        unprocessed_data = conn_obj._buffer.read()
                        logger.debug(
                            f"{conn_obj.name}: Compacting buffer from {buffer_size} to {len(unprocessed_data)} bytes."
                        )
                        conn_obj._buffer = io.BytesIO(unprocessed_data)

                except Exception as e:
                    logger.error(f"{conn_obj.name}: RTCM parsing failed ({e}).")
                    logger.error(f"Parser error: {conn_obj._rtcm_parser.last_error}")
                    # Clear buffer on error to prevent infinite loops
                    conn_obj._buffer = io.BytesIO()
        except Exception as e:
            logger.error(traceback.format_exc())
