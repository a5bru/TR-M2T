# TR-M2T
Protocol Transformer for MQTT and TCP

This repository demonstrates the use of MQTT for transmitting GNSS data by leveraging a protocol transformer. The project integrates Python with the Paho MQTT library, Mosquitto broker, and RTKLIB to facilitate seamless data conversion and transmission. It serves as a practical example for developers interested in combining MQTT with GNSS workflows for real-time applications.

Further descriptions and usage instructions can be found in the repository's Wiki.

In Order to run the example you have to define the following:

1. Define a data source (RTCM e.g. over TCP or Ntrip)
2. Start the Provider-Script (pub_data.sh)
3. Start the Consumer-Script (sub_data.sh)
