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
from pyrtcm import RTCMParseError, RTCMReader
from .metrics import STREAM_STATUS, BYTES_TRANSFERRED

from . import config
from .connection import DataConnection

logger = logging.getLogger(__name__)


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
    receiver.connect(f"tcp://localhost:{config.ZMQ_PULL_PORT}")

    o = urlparse(url)

    # Initialize MQTT Client with robust reconnect
    mqtt_client_id = f"n2m-{w_id:02d}-{w_pre}"
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id)
    if o.username and o.password:
        mqtt_client.username_pw_set(o.username, o.password)

    mqtt_connected: threading.Event = threading.Event()
    mqtt_should_stop: threading.Event = threading.Event()

    def on_connect(client: mqtt.Client, userdata: object, flags: Dict, rc: int, properties: Optional[object] = None) -> None:
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
        logger.warning(f"MQTT client {mqtt_client_id} could not connect after 10s, continuing anyway.")

    logger.info(f"Started MQTT client {mqtt_client_id}")

    while not run_event.is_set():
        try:
            fd, data = receiver.recv_pyobj()
            # logger.debug(f"Receiving data for fd={fd}, worker {w_id}, bytes={len(data)}")
        except Exception as e:
            logger.error(f"ZMQ receive error: {e}")
            time.sleep(1)
            continue

        if fd in connections:
            try:
                # The fd might be removed by hub concurrently; re-check
                conn_obj = connections.get(fd)
                if conn_obj is None:
                    continue

                conn_obj._buffer.write(data)
                conn_obj._buffer.seek(0)
                # url = conn_obj.url
                # o2 = urlparse(url)
                # p2 = o2.path[1:]
                p2 = conn_obj.name
                topic = f"{config.MQTT_TOPIC_PREFIX}/{p2}/rtcm"

                if config.PARSE_RAW:
                    try:
                        # Use RTCMReader to parse the stream
                        try:
                            rtr = RTCMReader(conn_obj._buffer)
                            for raw_data, parsed_data in rtr:
                                topic_m = f"{topic}/{parsed_data.identity}"
                                logger.debug(f"Topic: {topic_m}, Data: {len(raw_data)} bytes")
                                if mqtt_connected.is_set():
                                    mqtt_client.publish(topic_m, raw_data)
                        except:
                            if mqtt_connected.is_set():
                                topic_m = f"{topic}/0000" 
                                mqtt_client.publish(topic, conn_obj._buffer.getvalue())

                        # After processing, reset the buffer
                        conn_obj._buffer = io.BytesIO()

                    except RTCMParseError as e:
                        logger.error(f"RTCM Parse Error: {e}")
                        # If parsing fails, clear the buffer to start fresh
                        conn_obj._buffer = io.BytesIO()
                else:
                    # If not parsing, publish the raw data directly
                    if conn_obj._buffer.getbuffer().nbytes > 0:
                        if mqtt_connected.is_set():
                            mqtt_client.publish(topic, conn_obj._buffer.getvalue())
                        conn_obj._buffer = io.BytesIO()

            except Exception as e:
                logger.error(traceback.format_exc())

        time.sleep(0.000000001)

    mqtt_should_stop.set()
    mqtt_client.loop_stop()  # Stop the MQTT client loop
