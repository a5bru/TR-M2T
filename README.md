# TR-M2T

Protocol Transformer for MQTT and TCP

This repository demonstrates the use of MQTT for transmitting GNSS data by leveraging a protocol transformer. The project integrates Python with the Paho MQTT library, Mosquitto broker, and RTKLIB to facilitate seamless data conversion and transmission. It serves as a practical example for developers interested in combining MQTT with GNSS workflows for real-time applications.

In Order to run the example you have to define the following:

1. Checkout a Linux based system (e.g. Ubuntu, WSL, etc.)
2. Install Mosquitto MQTT Broker
3. Install a MQTT Explorer (optional)
4. Install RTKLIB
5. Define a data source (RTCM e.g. over TCP or Ntrip)
6. Start the Provider-Script (pub_data.sh)
7. Start the Consumer-Script (sub_data.sh)

Further descriptions and usage instructions can be found in the repository's [Wiki](https://github.com/a5bru/TR-M2T/wiki).

## Disclaimer

This code is provided "as is" without any warranties or guarantees of any kind. Use it at your own risk. The author is not responsible for any damage or loss that may occur through the use of this code. Always review and test the code thoroughly before using it in any production environment.

### Recommendation

It is strongly recommended to test this code in a controlled, non-production environment before deploying it to a live system. Ensure that all functionalities work as expected and that the code does not introduce any security vulnerabilities or performance issues.


## Issues and Contributions

If you have any questions, encounter issues, or have suggestions for improvements, please feel free to open an issue on this repository. We welcome contributions and feedback!

To open an issue:
1. Go to the [Issues](https://github.com/a5bru/TR-M2T/issues) tab of this repository.
2. Click on **New Issue**.
3. Provide a detailed description of the problem or improvement.

Your feedback is valuable and will help improve the project!

---

Thank you for your interest and contributions!
