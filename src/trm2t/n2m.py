#!/usr/bin/python3

# DISCLAIMER:
# This code is provided "as is" without any warranties or guarantees of any kind. Use it at your
# own risk. The author is not responsible for any damage or loss that may occur through the use
# of this code.
#
# Always review and test the code thoroughly before using it in any production environment.
#
# It is strongly recommended to test this code in a controlled, non-production environment
# before deploying it to a live system. Ensure that all functionalities work as expected and
# that the code does not introduce any security vulnerabilities or performance issues.


import sys
import os
import socket
import select
import time
import string
import random
import argparse
import paho.mqtt.client as mqtt
import base64
import logging
from dotenv import load_dotenv
from pyrtcm import RTCMReader

from trm2t import config
from . import config

logger = logging.getLogger(__name__)

BUFFER_SIZE = 1024*2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if os.path.exists(ENV_PATH):
    logger.info("Loading environment from: %s", ENV_PATH)

load_dotenv(ENV_PATH, verbose=False)

# Ntrip caster settings
NTRIP_HOST = os.environ.get("NTRIP_HOST", "127.0.0.1")
NTRIP_PORT = int(os.environ.get("NTRIP_PORT", 2101))
NTRIP_PATH = os.environ.get("NTRIP_PATH", "")

NTRIP_USER = os.environ.get("NTRIP_USER", "user")
NTRIP_PSWD = os.environ.get("NTRIP_PSWD", "pswd")

FMT_RTCM = "RTCM"
FMT_SBF = "SBF"
FMT_UBX = "UBX"
FMT_NONE = "NONE"

FMT_CHOICES = [
    FMT_RTCM,
    FMT_SBF,
    FMT_NONE,
]

parser = argparse.ArgumentParser()
# Settings for Ntrip
parser.add_argument("-H", default=NTRIP_HOST, type=str, help="Set the Ntrip host")
parser.add_argument("-P", default=NTRIP_PORT, type=int, help="Set the Ntrip port")
parser.add_argument("-D", default=NTRIP_PATH, type=str, help="Input Mountpoint")
parser.add_argument("-U", default=NTRIP_USER, type=str, help="Set the Ntrip user")
parser.add_argument("-W", default=NTRIP_PSWD, type=str, help="Set the Ntrip password")
# Settings for MQTT
parser.add_argument("-a", default=config.MQTT_HOST, type=str, help="Set the MQTT host")
parser.add_argument("-p", default=config.MQTT_PORT, type=int, help="Set the MQTT port")
parser.add_argument(
    "-m", default=config.MQTT_TOPIC_PREFIX, type=str, help="Set the root topic for the data"
)
parser.add_argument("-n", default=config.MQTT_USER, type=str, help="Set the MQTT username")
parser.add_argument("-c", default=config.MQTT_PSWD, type=str, help="Set the MQTTpassword")
# Settings for the Format
parser.add_argument("--timeout", default=15, type=int, help="Timeout with no data")
parser.add_argument(
    "--format",
    default=FMT_NONE,
    choices=FMT_CHOICES,
    help="Define the used format for parsing",
)
parser.add_argument(
    "--topic-per-type",
    action="store_true",
    help="Publish each message type under a special topic",
)
parser.add_argument(
    "--filter-allowed", action="store_true", help="Only publish allowed messages."
)
parser.add_argument(
    "--verbose", "-v", action="store_true", help="Enable verbose output"
)

args = parser.parse_args()


def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = "".join(random.choice(characters) for _ in range(length))
    return random_string


SOURCES_FILE = "sources.txt"
SOURCES_DICT = {}


def create_tcp_client(client_path, auth):
    # Create a TCP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (args.H, args.P)  # Replace with your server's IP and port

    try:
        if args.verbose:
            logger.info("C: connecting to %s:%s as %s", args.H, args.P, args.U)
        client_socket.connect(server_address)

    except BlockingIOError:
        # This is expected for non-blocking sockets
        pass

    try:
        request = f"GET /{client_path} HTTP/1.0\r\n"
        request += f"User-Agent: {config.USER_AGENT}\r\n"
        request += "Connection: close\r\n"
        request += f"Host: {args.H}\r\n"
        request += f"Authorization: Basic {auth}\r\n"
        request += "\r\n"
        client_socket.sendall(request.encode())
        seconds = 4.0
        readable, _, _ = select.select(
            [
                client_socket,
            ],
            [],
            [],
            seconds,
        )
        if not readable:
            assert False, f"E: {client_path}: No Response within {seconds} secs."
        data = client_socket.recv(BUFFER_SIZE)
        assert b"200" in data, f"E: {client_path}: {data[:20].decode()}"
        assert b"SOURCETABLE" not in data, f"E: {client_path}: not available"
        if args.verbose:
            logger.info("C: %s: Connected", client_path)
    except AssertionError as e:
        logger.error(e)
        return -1

    SOURCES_DICT[client_socket] = client_path
    client_socket.setblocking(0)  # Set socket to non-blocking
    return client_socket


def main():

    auth = base64.b64encode(f"{args.U}:{args.W}".encode()).decode()
    mqtt_client = None
    mqtt_connected = False
    ntrip_connected = False
    retry_delay = 5  # seconds
    max_retry_delay = 60  # seconds
    next_beat = time.time()
    keep_running = True

    def connect_mqtt():
        nonlocal mqtt_client, mqtt_connected
        while True:
            try:
                mqtt_client_id = f"n2m-{args.D}-{generate_random_string(8)}"
                mqtt_client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id
                )
                if args.n and args.c:
                    mqtt_client.username_pw_set(args.n, args.c)
                mqtt_client.connect(args.a, args.p)
                mqtt_client.loop_start()
                mqtt_connected = True
                if args.verbose:
                    logger.info("MQTT connected.")
                break
            except Exception as e:
                logger.error("MQTT connection failed: %s", e)
                mqtt_connected = False
                time.sleep(retry_delay)

    def connect_ntrip():
        nonlocal client_socket, ntrip_connected
        while True:
            client_socket = create_tcp_client(args.D, auth)
            if client_socket == -1:
                ntrip_connected = False
                logger.info("Retrying NTRIP connection in %s seconds...", retry_delay)
                time.sleep(retry_delay)
            else:
                ntrip_connected = True
                if args.verbose:
                    logger.info("NTRIP connected.")
                break

    connect_mqtt()
    connect_ntrip()
    next_beat = time.time()

    while keep_running:
        # Check MQTT connection
        if not mqtt_connected:
            if args.verbose:
                logger.info("Reconnecting MQTT...")
            connect_mqtt()
        # Check NTRIP connection
        if not ntrip_connected:
            if args.verbose:
                logger.info("Reconnecting NTRIP...")
            connect_ntrip()

        try:
            readable, _, _ = select.select([
                client_socket,
            ], [], [], 1.0)
            if readable:
                try:
                    if client_socket not in SOURCES_DICT:
                        logger.warning("W: unknown source %s", client_socket)
                        continue
                    topic = f"{config.MQTT_TOPIC_PREFIX}/{SOURCES_DICT[client_socket]}/rtcm"
                    data = client_socket.recv(BUFFER_SIZE)
                    if not data:
                        raise Exception(f"E: {args.D}: Empty response")
                    if args.verbose:
                        logger.info("P: %s: %s bytes", topic, len(data))
                    
                    if args.topic_per_type:
                        try:
                            msg = RTCMReader.parse(data)
                            logger.info("Identity: %s", msg.identity)
                            mqtt_client.publich(topic, msg.serialize())
                        except Exception as e:
                            logger.error("E: %s", e)
                    else:
                        mqtt_client.publish(topic, data)
                    next_beat = time.time()
                except Exception as e:
                    logger.error("NTRIP error: %s", e)
                    ntrip_connected = False
                    try:
                        client_socket.close()
                    except Exception:
                        pass
                    time.sleep(retry_delay)
            else:
                this_beat = time.time()
                if this_beat - next_beat > args.timeout:
                    logger.warning("W: No data %s, reconnecting NTRIP...", args.D)
                    ntrip_connected = False
                    try:
                        client_socket.close()
                    except Exception:
                        pass
                    time.sleep(retry_delay)
            time.sleep(0.1)
        except Exception as e:
            logger.error("Main loop error: %s", e)
            mqtt_connected = False
            ntrip_connected = False
            try:
                if client_socket:
                    client_socket.close()
            except Exception:
                pass
            try:
                if mqtt_client:
                    mqtt_client.loop_stop()
            except Exception:
                pass
            time.sleep(retry_delay)

    if mqtt_client:
        mqtt_client.loop_stop()
