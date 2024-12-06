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
import paho.mqtt.client as mqtt
import argparse

message_number = -1

parser = argparse.ArgumentParser()

# MQTT broker settings
BROKER_HOST = "HOST_IP"  # Change to your broker's address
BROKER_PORT = 1883          # Change if your broker uses a different port
TOPIC = "topic/data/RTCM"          # Change to your desired topic

# MQTT authentication settings
USERNAME = "USERNAME"  # Change to your MQTT username
PASSWORD = "PASSWORD"  # Change to your MQTT password

parser.add_argument("-a", default=BROKER_HOST)
parser.add_argument("-p", default=BROKER_PORT, type=int)
parser.add_argument("-m", default=TOPIC)
parser.add_argument("-n", default=USERNAME)
parser.add_argument("-c", default=PASSWORD)

args = parser.parse_args()

# Create an MQTT client
client = mqtt.Client()

# Set the username and password for authentication
client.username_pw_set(args.n, args.c)

# Connect to the broker
client.connect(args.a, args.p)

# The RTCM-parsing is based on
# https://github.com/aortner/RpiNtripBase/blob/master/rtcmadd1008.py

RTCM_PREFIX = b"\xd3"

try:
    # Continuously read from stdin
    while True:
        data = sys.stdin.buffer.read(1)

        # Find Preamble byte 0b11010011
        while data != RTCM_PREFIX: 
            data = sys.stdin.buffer.read(1)
            
        # 2 first bytes: 6 bits Reserved and 10 bits Message Length (0 - 1023 bytes)
        length_data = sys.stdin.buffer.read(2)
        
        # Masking away the first 6 Reserved  bits
        length = ((length_data[0] & 0b00000011) << 8) + length_data[1]
        packet_data = sys.stdin.buffer.read(length)
        crc24_data = sys.stdin.buffer.read(3)
        
        # Message Number (0 - 4095) is 12 first bits of the packet_data.
        if length >= 2:
            message_number = (packet_data[0] << 8) + packet_data[1]
            message_number >>= 4

        # Publish the parsed Message to MQTT
        client.publish(TOPIC, RTCM_PREFIX+length_data+packet_data+crc24_data)

except KeyboardInterrupt:
    print("Interrupted by user")

finally:
    # Disconnect from the broker
    client.disconnect()
