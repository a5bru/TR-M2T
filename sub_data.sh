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
MQTT_HOST="IP_OF_BROKER"
MQTT_PORT=1883
MQTT_USER="USERNAME"
MQTT_PSWD="PASSWORD"
MQTT_TOPIC="topic/data/RTCM"

# TCP/Ntrip server settings, replace with your settings
NTRIP_HOST="IP_OF_SOURCE"
NTRIP_PORT=2101
NTRIP_USER="USERNAME"
NTRIP_PSWD="PASSWORD"
NTRIP_PATH="MOUNTPOINT"		# WITHOUT SLASH!

TCP_PORT=6666

# Subscribe to the topic and forward it to RTKLIB/str2str
mosquitto_sub -h "${MQTT_HOST}" -p ${MQTT_PORT} \
		          -u "${USER}" -P "${PSWD}" \
				  -t "${TOPIC}" | str2str -out tcpsvr://:${TCP_PORT}
