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
MQTT_HOST="IP_OF_BROKER"
MQTT_PORT=1883
MQTT_USER="USERNAME"
MQTT_PSWD="PASSWORD"
MQTT_TOPIC="data"

# TCP/Ntrip server settings, replace with your settings
NTRIP_HOST="IP_OF_SOURCE"
NTRIP_PORT=2101
NTRIP_USER="USERNAME"
NTRIP_PSWD="PASSWORD"
NTRIP_PATH="MOUNTPOINT"		# WITHOUT SLASH!

TCP_PORT=6666
FORMAT="NONE"

# Load the .env file
if [ -f m2t.env ]; then
  export $(grep -v '^#' m2t.env | xargs)
fi

# Subscribe to the topic and forward it to RTKLIB/str2str
#mosquitto_sub -h "${MQTT_HOST}" -p ${MQTT_PORT} -t "${MQTT_TOPIC}" -u "${MQTT_USER}" -P "${MQTT_PSWD}"

echo python3 sub_data.py -a "${MQTT_HOST}" -p $MQTT_PORT -m "${MQTT_TOPIC}" -n "${MQTT_USER}" -c "${MQTT_PSWD}" --format "${FORMAT}"
python3 sub_data.py -a "${MQTT_HOST}" -p $MQTT_PORT -m "${MQTT_TOPIC}" -n "${MQTT_USER}" -c "${MQTT_PSWD}" --format "${FORMAT}"

