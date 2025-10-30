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
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if os.path.exists(ENV_PATH):
    print("Loading environment from:", ENV_PATH)

load_dotenv(ENV_PATH, verbose=False)

# MQTT broker settings
# Change to your broker's address
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
# Change if your broker uses a different port
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
# Change to your desired topic path
MQTT_PATH = os.environ.get("MQTT_PATH", "data")

# MQTT authentication settings
# Change to your MQTT username
MQTT_USER = os.environ.get("MQTT_USER", "")
# Change to your MQTT password
MQTT_PSWD = os.environ.get("MQTT_PSWD", "")

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
parser.add_argument("-a", default=MQTT_HOST, type=str, help="Set the MQTT host")
parser.add_argument("-p", default=MQTT_PORT, type=int, help="Set the MQTT port")
parser.add_argument(
    "-m", default=MQTT_PATH, type=str, help="Set the root topic for the data"
)
parser.add_argument("-n", default=MQTT_USER, type=str, help="Set the MQTT username")
parser.add_argument("-c", default=MQTT_PSWD, type=str, help="Set the MQTTpassword")
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
print(args)


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
            print(f"C: connecting to {args.H}:{args.P} as {args.U}")
        client_socket.connect(server_address)

    except BlockingIOError:
        # This is expected for non-blocking sockets
        pass

    try:
        request = f"GET /{client_path} HTTP/1.0\r\n"
        request += "User-Agent: Ntrip N2Mqtt/v0.1\r\n"
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
        data = client_socket.recv(1024)
        assert b"200" in data, f"E: {client_path}: {data[:20].decode()}"
        assert b"SOURCETABLE" not in data, f"E: {client_path}: not available"
        if args.verbose:
            print(f"C: {client_path}: Connected")
    except AssertionError as e:
        print(e, file=sys.stderr)
        return -1

    SOURCES_DICT[client_socket] = client_path
    client_socket.setblocking(0)  # Set socket to non-blocking
    return client_socket


def main():

    auth = base64.b64encode(f"{args.U}:{args.W}".encode()).decode()
    if args.verbose:
        print(f"C: connecting to {args.H}:{args.P} as {args.U}")
    client_socket = create_tcp_client(args.D, auth)
    if client_socket == -1:
        sys.exit(1)

    # Initialize MQTT Client
    mqtt_client_id = f"n2m-{args.D}-{generate_random_string(8)}"
    mqtt_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id
    )
    if args.n and args.c:
        mqtt_client.username_pw_set(args.n, args.c)

    mqtt_client.connect(args.a, args.p)

    keep_running = True
    next_beat = time.time()
    mqtt_client.loop_start()  # Start the MQTT client loop

    while keep_running:
        # Use select to wait for any socket to be ready for processing
        readable, _, _ = select.select(
            [
                client_socket,
            ],
            [],
            [],
            1.0,
        )
        if readable:
            try:
                # Get topic for client or skip
                if client_socket not in SOURCES_DICT:
                    print("W: unknown source", client_socket)
                    continue
                topic = f"s2d/osr/{SOURCES_DICT[client_socket]}/rtcm"
                data = client_socket.recv(1024)
                assert len(data) > 0, f"E: {args.D}: Empty response"
                # Publish received data to MQTT
                if args.verbose:
                    print(f"P: {topic}: {len(data)} bytes")
                mqtt_client.publish(topic, data)
                next_beat = time.time()
            except Exception as e:
                print(e, file=sys.stderr)
        else:
            this_beat = time.time()
            if this_beat - next_beat > args.timeout:
                print(f"W: No data {args.D}")
                keep_running = False
        time.sleep(0.1)

    mqtt_client.loop_stop()  # Stop the MQTT client loop


if __name__ == "__main__":
    main()  # Run the main function
