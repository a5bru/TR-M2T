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
import argparse
import paho.mqtt.client as mqtt

# Configuration
BROKER_HOST = "broker.example.com"  # Replace with your broker's address
BROKER_PORT = 1883                     # Default MQTT port (or 8883 for TLS)
USERNAME = "your_username"             # Replace with your username
PASSWORD = "your_password"             # Replace with your password
TOPIC = "example/topic"                # Replace with the topic you want to subscribe to

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
parser.add_argument("-a", default=BROKER_HOST, type=str, help="Set the host of the MQTT broker")
parser.add_argument("-p", default=BROKER_PORT, type=int, help="Set the port of the MQTT broker")
parser.add_argument("-m", default=TOPIC, type=str, help="Set the root topic for the data")
parser.add_argument("-n", default=USERNAME, type=str, help="Set the username")
parser.add_argument("-c", default=PASSWORD, type=str, help="Set the password")
parser.add_argument("--format", default=FMT_NONE, choices=FMT_CHOICES, help="Define the used format for parsing")
parser.add_argument("--topic-per-type", action="store_true", help="Publish each message type under a special topic")

args = parser.parse_args()

# Callback for when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker successfully!")
        print(f"Subscribing to topic: {args.m}")
        client.subscribe(args.m)
    else:
        print(f"Failed to connect, return code {rc}")

# Callback for when a message is received
def on_message(client, userdata, msg):
    #print(f"Message received on topic {msg.topic}: {msg.payload.decode()}")
    sys.stdout.buffer.write(msg.payload)
    sys.stdout.buffer.flush()

# Create an MQTT client instance
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)

# Set username and password
if args.n and args.c:
    client.username_pw_set(args.n, args.c)

# Attach callback functions
client.on_connect = on_connect
client.on_message = on_message

try:
    # Connect to the broker
    print(f"Connecting to broker at {args.a}:{args.p}")
    client.connect(args.a, args.p, 60)

    # Start the network loop
    client.loop_forever()
except KeyboardInterrupt:
    print("\nDisconnecting...")
    client.disconnect()
except Exception as e:
    print(f"An error occurred: {e}")

