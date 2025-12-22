import io
import random
import string
import threading
import time
import traceback
import logging
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import setproctitle
import zmq
from pyrtcm import RTCMParseError, RTCMReader
from .metrics import STREAM_STATUS, BYTES_TRANSFERRED

from . import config

logger = logging.getLogger(__name__)


def generate_random_string(length: int):
    characters = string.ascii_letters + string.digits
    random_string = "".join(random.choice(characters) for _ in range(length))
    return random_string


def worker(name: str, w_id: int, url: str, run_event: threading.Event, context: zmq.Context, connections: dict):
    setproctitle.setproctitle(name)
    logger.info(f"Thread {name}")

    receiver = context.socket(zmq.PULL)
    receiver.connect(f"tcp://localhost:{config.ZMQ_PULL_PORT}")

    o = urlparse(url)

    # Initialize MQTT Client with robust reconnect
    mqtt_client_id = f"n2m-{w_id:02d}-{generate_random_string(8)}"
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id)
    if o.username and o.password:
        mqtt_client.username_pw_set(o.username, o.password)

    mqtt_connected = threading.Event()
    mqtt_should_stop = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"MQTT client {mqtt_client_id} connected.")
            mqtt_connected.set()
        else:
            logger.error(f"MQTT client {mqtt_client_id} failed to connect, rc={rc}")
            mqtt_connected.clear()

    def on_disconnect(client, userdata, rc, properties=None, reason_code=None):
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
                url = conn_obj.url
                o2 = urlparse(url)
                p2 = o2.path[1:]
                topic = f"{config.MQTT_TOPIC_PREFIX}/{p2}/rtcm"

                if config.PARSE_RAW:
                    try:
                        # Use RTCMReader to parse the stream
                        rtr = RTCMReader(conn_obj._buffer)
                        for raw_data, parsed_data in rtr:
                            topic_m = f"{topic}/{parsed_data.identity}"
                            logger.debug(f"Topic: {topic_m}, Data: {len(raw_data)} bytes")
                            if mqtt_connected.is_set():
                                mqtt_client.publish(topic_m, raw_data)

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
