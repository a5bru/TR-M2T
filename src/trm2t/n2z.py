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
# import os
import socket
import select
import time
import argparse
import base64
import zmq

# Ntrip caster settings
NTRIP_HOST = "127.0.0.1"
NTRIP_PORT = 2101
NTRIP_PATH = ""

NTRIP_USER = "user"
NTRIP_PSWD = "pswd"

# ZMQ settings
ZMQ_PORT=5556
ZMQ_HOST="localhost"

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
# Settings for ZMQ
parser.add_argument("-z", default=ZMQ_PORT, type=int, help="Set the ZMQ port")
parser.add_argument("-k", default=ZMQ_HOST, type=str, help="Set the ZMQ host")
# Settings for the Format
parser.add_argument("--format", default=FMT_NONE, choices=FMT_CHOICES, help="Define the used format for parsing")
parser.add_argument("--topic-per-type", action="store_true", help="Publish each message type under a special topic")
parser.add_argument("--filter-allowed", action="store_true", help="Only publish allowed messages.")

args = parser.parse_args()

SOURCES_DICT = {}

def create_tcp_client(client_path, auth):
    # Create a TCP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (args.H, args.P)  # Replace with your server's IP and port

    try:
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
        data = client_socket.recv(2048)
        assert b"200" in data, f"E: {client_path}: {data[:20].decode()}"
        assert b"SOURCETABLE" not in data, f"E: {client_path}: not available"
        print(data)
        print("Source OK %s" % client_path)
    except AssertionError as e:
        return -1

    SOURCES_DICT[client_socket] = client_path
    return client_socket


def main():

    sources_list = []
    auth = base64.b64encode(f"{args.U}:{args.W}".encode()).decode()
    client_socket = create_tcp_client(args.D, auth)
    if client_socket == -1:
        sys.exit(1)
    clients = [client_socket, ]

    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect(f"tcp://{args.k}:{args.z}")  # Bind to a TCP port

    keep_running = True
    while keep_running:
        # Use select to wait for any socket to be ready for processing
        readable, _, _ = select.select([client_socket, ], [], [], 1.0)
        if readable:
            topic = f"s2d/osr/{SOURCES_DICT[client_socket]}/rtcm"
            data = client_socket.recv(1024)
            if data:
                # Publish received data to MQTT
                publisher.send_multipart([topic.encode(), data])  # Send topic and message
                print(f"Published: {topic} from client {args.D}")
        time.sleep(0.0001)


if __name__ == "__main__":
    main()  # Run the main function

