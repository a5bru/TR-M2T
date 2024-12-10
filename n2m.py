#!/usr/bin/python3

# DISCLAIMER:
# This script is provided "as is" without any warranties or guarantees of any
# kind, express or implied. Use of this script is at your own risk. The 
# author(s) of this code are not responsible for any direct,  indirect, 
# incidental, or consequential damages resulting from its use.
#
# It is strongly recommended to review, test, and verify this script in a
# controlled environment before using it in any production or critical systems.
#
# By using this script, you acknowledge and agree to these terms.

import sys
import os
import socket
import select
import time
import argparse
import paho.mqtt.client as mqtt
import base64

# MQTT broker settings
MQTT_HOST = "127.0.0.1"  # Change to your broker's address
MQTT_PORT = 1883          # Change if your broker uses a different port
MQTT_PATH = "data"          # Change to your desired topic

# MQTT authentication settings
MQTT_USER = ""  # Change to your MQTT username
MQTT_PSWD = ""  # Change to your MQTT password

# Ntrip caster settings
NTRIP_HOST = "127.0.0.1"
NTRIP_PORT = 2101
NTRIP_PATH = ""

NTRIP_USER = "user"
NTRIP_PSWD = "pswd"

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
parser.add_argument("-m", default=MQTT_PATH, type=str, help="Set the root topic for the data")
parser.add_argument("-n", default=MQTT_USER, type=str, help="Set the MQTT username")
parser.add_argument("-c", default=MQTT_PSWD, type=str, help="Set the MQTTpassword")
# Settings for the Format
parser.add_argument("--format", default=FMT_NONE, choices=FMT_CHOICES, help="Define the used format for parsing")
parser.add_argument("--topic-per-type", action="store_true", help="Publish each message type under a special topic")
parser.add_argument("--filter-allowed", action="store_true", help="Only publish allowed messages.")

args = parser.parse_args()

# Initialize MQTT Client
mqtt_client = mqtt.Client()
mqtt_client.connect(args.a, args.p)

SOURCES_FILE = "sources.txt"
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
        data = client_socket.recv(1024)
        assert b"200" in data, f"E: {client_path}: {data[:20].decode()}"
        assert b"SOURCETABLE" not in data, f"E: {client_path}: not available"
        print("Source OK %s" % client_path)
    except AssertionError as e:
        return -1

    SOURCES_DICT[client_socket] = client_path
    client_socket.setblocking(0)  # Set socket to non-blocking
    return client_socket


def main():

    sources_list = []
    auth = base64.b64encode(f"{args.U}:{args.W}".encode()).decode()
    client_socket = create_tcp_client(args.D, auth)
    if client_socket == -1:
        sys.exit(1)
    clients = [client_socket, ]

    keep_running = True
    while keep_running:
        # Use select to wait for any socket to be ready for processing
        readable, _, _ = select.select(clients, [], [], 15.0)

        for s in readable:
            if s in clients:
                try:
                    # Get topic for client or skip
                    if s not in SOURCES_DICT:
                        print("W: unknown source", s)
                        continue
                    topic = f"s2d/osr/{SOURCES_DICT[s]}/rtcm"
                    data = s.recv(1024)
                    if data:
                        # Publish received data to MQTT
                        mqtt_client.publish(topic, data)
                        # print(f"Published: {topic} from client {clients.index(s)}")
                except Exception as e:
                    print(e) 
        time.sleep(0.000001)


if __name__ == "__main__":
    mqtt_client.loop_start()  # Start the MQTT client loop
    main()  # Run the main function
    mqtt_client.loop_stop()  # Stop the MQTT client loop

