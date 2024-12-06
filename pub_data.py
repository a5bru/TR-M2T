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

# MQTT broker settings
BROKER_HOST = "127.0.0.1"  # Change to your broker's address
BROKER_PORT = 1883          # Change if your broker uses a different port
TOPIC = "data"          # Change to your desired topic

# MQTT authentication settings
USERNAME = ""  # Change to your MQTT username
PASSWORD = ""  # Change to your MQTT password

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

BUFFER_READ_SIZE = 1024
PRE_RTCM = b"\xd3"
PRE_UBX = b"\xb5\x62"
PRE_SBF = b"\x24\x40"

ALLOWED_MESSAGES_RTCM = [
    1001, 1002, 1003,
    1005, 1006, 1007, 1008, 1009, 1010, 1011,
    1004, 1012, 1013,
    1019, 1020,
    1029,
    1032, 1033, 1034, 1035,
    1041, 1042, 1044, 1045, 1046,
    1071, 1081, 1091, 1101, 1111, 1121, 1131,
    1072, 1082, 1092, 1102, 1112, 1122, 1132,
    1073, 1083, 1093, 1103, 1113, 1123, 1133,
    1074, 1084, 1094, 1104, 1114, 1124, 1134,
    1075, 1085, 1095, 1105, 1115, 1125, 1135,
    1076, 1086, 1096, 1106, 1116, 1126, 1136,
    1077, 1087, 1097, 1107, 1117, 1127, 1137,
    1230,
]

message_number = -1

# Create an MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

# Set the username and password for authentication
if args.n and args.c:
    client.username_pw_set(args.n, args.c)

# Connect to the broker
client.connect(args.a, args.p)

# The RTCM-parsing is based on
# https://github.com/aortner/RpiNtripBase/blob/master/rtcmadd1008.py

try:
    topic = args.m
    
    # Continuously read from stdin
    while True:

        # Handle RTCM Format
        if args.format == FMT_RTCM:
            
            data = sys.stdin.buffer.read(1)    
            # Find Preamble byte 0b11010011
            while data != PRE_RTCM: 
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

            if message_number not in ALLOWED_MESSAGES_RTCM:
                continue
            # Add Message Type info to topic
            topic = args.m
            if args.topic_per_type:
                topic += f"/{message_number:04d}"
                
            # Putting the bytes together
            data = PRE_RTCM + length_data + packet_data + crc24_data

        # TODO Handle Septentrio's SBF Format, not tested!
        elif args.format == FMT_SBF:
            
            data = sys.stdin.buffer.read(1)            
            # Find Preamble byte x24
            while data != PRE_SBF[0]: 
                data = sys.stdin.buffer.read(1)
            # Find Preamble byte x40
            data = sys.stdin.buffer.read(1)
            if data != PRE_SBF[1]:
                continue
            # Message Checksum
            crc_data = sys.stdin.buffer.read(2)
            # Message Id
            id_data = sys.stdin.buffer.read(2)
            # Message Length
            length_data = sys.stdin.buffer.read(2)
            length = (length_data[0] << 8) + length_data[1]
            if length % 4 != 0:
                continue
            # Read the payload
            payload_data = sys.stdin.buffer.read(length)

            # Putting the bytes together
            data = PRE_SBF + crc_data + id_data + length_data + payload_data            
           
        # TODO Handle U-blox' UBX Format, not tested!
        elif args.format == FMT_UBX:
            
            data = sys.stdin.buffer.read(1)    
            # Find Preamble byte xb5
            while data != PRE_UBX[0]: 
                data = sys.stdin.buffer.read(1)
            # Find Preamble byte x62
            data = sys.stdin.buffer.read(1)
            if data != PRE_UBX[1]:
                continue
            # Message Class
            class_data = sys.stdin.buffer.read(1)
            # Message Id
            id_data = sys.stdin.buffer.read(1)
            # Message Length
            length_data = sys.stdin.buffer.read(2)
            length = (length_data[0] << 8) + length_data[1]
            # Message Payload
            payload_data = sys.stdin.buffer.read(length)
            # Checksum
            cka_data = sys.stdin.buffer.read(1)
            ckb_data = sys.stdin.buffer.read(1)

            # Putting the bytes together
            data = PRE_UBX + class_data + id_data + length_data + payload_data + cka_data + ckb_data

        # Handle Unformatted stream
        else:
            
            data = sys.stdin.buffer.read(BUFFER_READ_SIZE)

        # Publish the parsed Message to MQTT
        client.publish(topic, data)

except KeyboardInterrupt:
    print("Interrupted by user")

finally:
    # Disconnect from the broker
    client.disconnect()
