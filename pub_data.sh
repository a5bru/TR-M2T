#!/bin/bash

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

NTRIP_PATH_ARG="$1"

if [ -z "$NTRIP_PATH_ARG" ]; then
    NTRIP_PATH_USE=$NTRIP_PATH
    MQTT_TOPIC_USE=$MQTT_TOPIC
else
    NTRIP_PATH_USE=$NTRIP_PATH_ARG
    MQTT_TOPIC_USE=s2d/osr/${NTRIP_PATH_USE}/rtcm
fi

# Connect to the Ntrip server and publish it with MQTT-Paho client
#python3 n2z.py \
#     -H "${NTRIP_HOST}" -P $NTRIP_PORT \
#     -D "${NTRIP_PATH_USE}" \
#     -U "${NTRIP_USER}" -W "${NTRIP_PSWD}" \
#     --format "${FORMAT}"
python3 n2m.py \
     -H "${NTRIP_HOST}" -p $NTRIP_PORT \
     -D "${NTRIP_PATH_USE}" \
     -U "${NTRIP_USER}" -W "${NTRIP_PSWD}" \
     -a "${MQTT_HOST}" -p $MQTT_PORT \
     -n "${MQTT_USER}" -c "${MQTT_PSWD}" \
     -m "${MQTT_TOPIC_USE}" --format "${FORMAT}"

#echo curl -v -A "Ntrip cURL" --user "${NTRIP_USER}:${NTRIP_PSWD}" http://${NTRIP_HOST}:${NTRIP_PORT}/${NTRIP_PATH_USE} --http0.9 --output -
#curl -v -A "Ntrip cURL" --user "${NTRIP_USER}:${NTRIP_PSWD}" http://${NTRIP_HOST}:${NTRIP_PORT}/${NTRIP_PATH_USE} --no-buffer --http0.9 --output - | \
#        python3 pub_data.py -a "${MQTT_HOST}" -p $MQTT_PORT -m "${MQTT_TOPIC_USE}" -n "${MQTT_USER}" -c "${MQTT_PSWD}" --format "${FORMAT}"
