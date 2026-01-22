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
import logging

from . import config

logger = logging.getLogger(__name__)

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
parser.add_argument(
    "-a", default=config.MQTT_HOST, type=str, help="Set the host of the MQTT broker"
)
parser.add_argument(
    "-p", default=config.MQTT_PORT, type=int, help="Set the port of the MQTT broker"
)
parser.add_argument(
    "-m", default=config.MQTT_TOPIC_PREFIX, type=str, help="Set the root topic for the data"
)
parser.add_argument("-n", default=config.MQTT_USER, type=str, help="Set the username")
parser.add_argument("-c", default=config.MQTT_PSWD, type=str, help="Set the password")
parser.add_argument(
    "--format", default=FMT_NONE, choices=FMT_CHOICES, help="Define the used format for parsing"
)
parser.add_argument(
    "--topic-per-type", action="store_true", help="Publish each message type under a special topic"
)

args = parser.parse_args()


# Callback for when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker successfully!")
        logger.info(f"Subscribing to topic: {args.m}")
        client.subscribe(args.m)
    else:
        logger.error(f"Failed to connect, return code {rc}")


# Callback for when a message is received
def on_message(client, userdata, msg):
    # logger.debug(f"Message received on topic {msg.topic}: {msg.payload.decode()}")
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
    logger.info(f"Connecting to broker at {args.a}:{args.p}")
    client.connect(args.a, args.p, 60)

    # Start the network loop
    client.loop_forever()
except KeyboardInterrupt:
    logger.info("Disconnecting...")
    client.disconnect()
except Exception as e:
    logger.error(f"An error occurred: {e}")
