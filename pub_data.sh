#!/bin/bash

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

# MQTT broker settings, replace with your settings
MQTT_HOST="HOST_IP1"
MQTT_PORT=1883
MQTT_USER="USERNAME"
MQTT_PSWD="PASSWORD"
MQTT_TOPIC="topic/data/RTCM"

# TCP/Ntrip server settings, replace with your settings
NTRIP_HOST="HOST_IP2"
NTRIP_PORT=2101
NTRIP_USER="USERNAME2"
NTRIP_PSWD="PASSWORD2"
NTRIP_PATH="MP1"              # WITHOUT SLASH!

FORMAT="NONE"

# Load the .env file
if [ -f m2t.env ]; then
  export $(grep -v '^#' m2t.env | xargs)
fi

# Connect to the Ntrip server and publish it with MQTT-Paho client
str2str -in ntrip://${NTRIP_USER}:${NTRIP_PSWD}@${NTRIP_HOST}:${NTRIP_PORT}/${NTRIP_PATH} | \
	python3 pub_data.py -a "${MQTT_HOST}" -p $MQTT_PORT -m "${MQTT_TOPIC}" -n "${MQTT_USER}" -c "${MQTT_PSWD}" --format "${FORMAT}"

#curl -A "Ntrip cURL" --user "${NTRIP_USER}:${NTRIP_PSWD}" http://${NTRIP_HOST}:${NTRIP_PORT}/${NTRIP_PATH} --http0.9 --output - | \
#        python3 pub_data.py -a "${MQTT_HOST}" -p $MQTT_PORT -m "${MQTT_TOPIC}" -n "${MQTT_USER}" -c "${MQTT_PSWD}" --format "${FORMAT}"
