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
import base64
import paho.mqtt.client as mqtt
import zmq

# MQTT broker settings
MQTT_HOST = "127.0.0.1"  # Change to your broker's address
MQTT_PORT = 1883          # Change if your broker uses a different port
MQTT_PATH = "data"          # Change to your desired topic

# MQTT authentication settings
MQTT_USER = ""  # Change to your MQTT username
MQTT_PSWD = ""  # Change to your MQTT password

# ZMQ settings
ZMQ_PORT = 5556

parser = argparse.ArgumentParser()
# Settings for MQTT
parser.add_argument("-a", default=MQTT_HOST, type=str, help="Set the MQTT host")
parser.add_argument("-p", default=MQTT_PORT, type=int, help="Set the MQTT port")
parser.add_argument("-n", default=MQTT_USER, type=str, help="Set the MQTT username")
parser.add_argument("-c", default=MQTT_PSWD, type=str, help="Set the MQTTpassword")
# Settings for ZMQ
parser.add_argument("-z", default=ZMQ_PORT, type=int, help="Set the ZMQ port")


args = parser.parse_args()

# Initialize MQTT Client
mqtt_client = mqtt.Client()
mqtt_client.connect(args.a, args.p)

def main():
    context = zmq.Context()
    next_beat = time.time()
    subscriber = context.socket(zmq.SUB)
    subscriber.bind(f"tcp://*:{args.z}")  # Connect to the publisher
    subscriber.setsockopt_string(zmq.SUBSCRIBE, "s2d/osr")  # Subscribe to all topics

    while True:
        if next_beat < time.time():
            print("ALIVE")
            next_beat = time.time() + 10 

        poller = zmq.Poller()
        poller.register(subscriber, zmq.POLLIN)  # Register the subscriber for incoming messages

        # Poll for events
        socks = dict(poller.poll(1000))  # Timeout of 1000 ms

        if subscriber in socks and socks[subscriber] == zmq.POLLIN:
            topic, message = subscriber.recv_multipart()  # Receive topic and message
            mqtt_client.publish(topic.decode(), message)
            #print(f"Published: {topic.decode()} - {len(message)}")
        else:
            print("No messages received, doing other work...")
            # Here you can perform other tasks or just wait
            time.sleep(1)  # Simulate doing other work

if __name__ == "__main__":
    main()
