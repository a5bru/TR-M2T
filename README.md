# TR-M2T

**GNSS Data Protocol Transformer for NTRIP, MQTT, and TCP**

TR-M2T is a robust hub application that bridges NTRIP (Networked Transport of RTCM via Internet Protocol) streams with MQTT, enabling real-time GNSS correction data distribution for RTK (Real-Time Kinematic) positioning systems. The project provides scalable connection management, automatic reconnection handling, and optional RTCM message parsing.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Monitoring](#monitoring)
- [Advanced Features](#advanced-features)

---

## Overview

TR-M2T acts as a central hub that:
- **Connects** to multiple NTRIP casters (or raw TCP streams) simultaneously
- **Manages** connection lifecycles with exponential backoff and automatic reconnection
- **Distributes** GNSS correction data to MQTT topics for downstream consumers
- **Monitors** stream health with Prometheus metrics
- **Scales** with parallel connection handling and worker threads

### Key Features

✅ **Multi-Protocol Support**: NTRIP and raw TCP connections  
✅ **Database-Driven Configuration**: SQLite-based mountpoint management  
✅ **Automatic Reconnection**: Exponential backoff for failed connections  
✅ **Parallel Processing**: Thread pool for connection creation, worker threads for data distribution  
✅ **Optional RTCM Parsing**: Parse and validate RTCM messages with pyrtcm  
✅ **Prometheus Metrics**: Monitor stream status, bytes transferred, and connection health  
✅ **Flexible MQTT Publishing**: Configurable topics and QoS settings  
✅ **TCP Relay Output**: Optional per-mountpoint TCP servers for direct clients  

---

## Architecture

```
┌─────────────────┐
│  NTRIP Caster   │◄──── Connection 1
└─────────────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐      ┌─────────────┐
│  TR-M2T Hub     │◄────►│  SQLite DB   │      │ Prometheus  │
│  (run.py)       │      │  (mounts)    │      │  Metrics    │
└─────────────────┘      └──────────────┘      └─────────────┘
    │        │
    │        ▼
    │   ┌─────────────────┐
    │   │  Worker Threads │
    │   │  (ZMQ + MQTT)   │
    │   └─────────────────┘
    │            │
    ▼            ▼
┌─────────────────┐      ┌─────────────┐
│  NTRIP Caster   │      │ MQTT Broker │
│  (Connection N) │      │ (Mosquitto) │
└─────────────────┘      └─────────────┘
                              │
                              ▼
                         ┌─────────────┐
                         │ MQTT        │
                         │ Subscribers │
                         └─────────────┘
```

### Components

1. **Hub Module** (`hub.py`): Manages mountpoint connections, monitors database for active mountpoints, handles socket events
2. **Connection Module** (`connection.py`): Establishes TCP/NTRIP connections with authentication
3. **Worker Module** (`worker.py`): Receives data via ZMQ, publishes to MQTT topics
4. **Database Module** (`db.py`): SQLite operations for mountpoint CRUD
5. **Metrics Module** (`metrics.py`): Prometheus exporters for monitoring

---

## How It Works

### 1. **Mountpoint Management**

The hub periodically queries the database for **active mountpoints**. Each mountpoint represents a connection to an NTRIP caster or TCP stream:

```python
# Database Schema
mountpoints (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,           # e.g., "BASE_STATION_1"
    connection_string TEXT,     # e.g., "ntrip://user:pass@caster.example.com:2101/MOUNT1"
    active INTEGER,             # 1 = active, 0 = inactive
    timeout INTEGER             # Connection timeout in seconds
)
```

### 2. **Connection Establishment**

For each active mountpoint:
- **Parse** the connection string (supports `ntrip://` and `tcp://` schemes)
- **Create** a TCP socket with timeout
- **Send** NTRIP authentication request (if using NTRIP protocol)
- **Validate** server response (expects "ICY 200 OK" or "HTTP 200")
- **Register** the socket with the event selector for data reading

### 3. **Data Flow**

```
NTRIP Stream → Socket → Selector (epoll/kqueue) → ZMQ Push → Worker Threads → MQTT Publish
```

1. **Event Loop**: The hub uses `selectors` to monitor multiple sockets for incoming data
2. **Data Reception**: When data arrives, it's read into a buffer
3. **ZMQ Distribution**: Data is pushed to a ZMQ PULL socket
4. **Worker Processing**: Worker threads pull data, optionally parse RTCM messages, and publish to MQTT
5. **MQTT Topics**: Data is published to topics like `{prefix}/{mountpoint}` (e.g., `s2d/osr/BASE_1`)

### 4. **Failure Handling**

- **Connection Failures**: Exponential backoff (2s, 4s, 8s, 16s...) up to `HUB_MAX_INACTIVE_COUNT` retries
- **Data Timeouts**: Sockets have configurable timeouts (default 15s)
- **MQTT Reconnection**: Workers automatically reconnect to MQTT broker on disconnection
- **Graceful Shutdown**: Cleans up connections and threads on SIGINT/SIGTERM

---

## Installation

### Prerequisites

- **Linux-based system** (Ubuntu, Debian, WSL, etc.)
- **Python 3.9+**
- **Mosquitto MQTT Broker** (or another MQTT broker)

### Install System Dependencies

```bash
# Install Mosquitto MQTT Broker
sudo apt update
sudo apt install mosquitto mosquitto-clients

# Start Mosquitto
sudo systemctl start mosquitto
sudo systemctl enable mosquitto
```

### Install Python Dependencies

```bash
# Clone the repository
git clone https://github.com/a5bru/TR-M2T.git
cd TR-M2T

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Initialize Database

```bash
# Create the SQLite database and mountpoints table
python scripts/init_db.py
```

---

## Configuration

TR-M2T uses environment variables for configuration. Create a `.env` file in the project root:

```bash
# Database
TRM2T_DATABASE=mountpoints.db

# MQTT Broker
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=your_username
MQTT_PSWD=your_password
MQTT_PATH=s2d/osr              # Topic prefix

# Hub Settings
MQTT_HUB_WORKERS=4             # Number of MQTT worker threads
HUB_CREATION_LOADERS=8         # Parallel connection creation threads
HUB_MAX_INACTIVE_COUNT=10      # Max retries before disabling mountpoint

# ZMQ
ZMQ_PULL_PORT=6969             # Port for inter-thread communication

# Optional: RTCM Parsing
TRM2T_PARSE_RAW=false          # Set to 'true' to parse RTCM messages

# Optional: TCP relay (per mountpoint)
TRM2T_TCP_RELAY=true           # Start a TCP server for each active mountpoint
TRM2T_TCP_RELAY_BASE_PORT=24000 # Listening port = BASE_PORT + mountpoint id
TRM2T_TCP_RELAY_BIND=0.0.0.0    # Bind address for TCP relay
TRM2T_TCP_RELAY_BACKLOG=8       # Max pending connections per relay
TRM2T_TCP_RELAY_QUEUE=5000      # Buffered messages per relay before drop

# Prometheus Metrics
PROM_PORT=8000                 # Metrics endpoint port

# Logging
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
```

---

## Quick Start

### 1. Add a Mountpoint

```bash
# Add an NTRIP mountpoint
python scripts/add_mountpoint.py \
  --name "BASE_STATION_1" \
  --connection "ntrip://username:password@caster.example.com:2101/MOUNT1" \
  --active 1 \
  --timeout 15

# Add a raw TCP stream
python scripts/add_mountpoint.py \
  --name "TCP_STREAM" \
  --connection "tcp://192.168.1.100:5000" \
  --active 1
```

### 2. Start the Hub

```bash
python run.py
```

You should see logs indicating:
```
2026-01-21 18:00:00 - trm2t.hub - INFO - Check for active mountpoints
2026-01-21 18:00:00 - trm2t.connection - INFO - I: BASE_STATION_1: Opening connection (fd=5)
2026-01-21 18:00:01 - trm2t.worker - INFO - Worker-1 connected to MQTT broker
```

### 3. Subscribe to Data

In another terminal:

```bash
# Subscribe to all topics under the prefix
mosquitto_sub -h localhost -t "s2d/osr/#" -v

# Or subscribe to a specific mountpoint
mosquitto_sub -h localhost -t "s2d/osr/MOUNT1" -v
```

---

## Usage Examples

### Example 1: Single NTRIP Connection

**Scenario**: Connect to a public NTRIP caster and republish data to MQTT.

```bash
# Initialize database
python scripts/init_db.py

# Add mountpoint
python scripts/add_mountpoint.py \
  --name "BKG_FFMZ1" \
  --connection "ntrip://user:pass@www.igs-ip.net:2101/FFMZ1" \
  --active 1

# Start hub
python run.py
```

**MQTT Output**: Data appears on topic `s2d/osr/FFMZ1`

---

### Example 2: Multiple Mountpoints with Different Casters

```bash
# Add multiple mountpoints
python scripts/add_mountpoint.py --name "CASTER_A_MP1" \
  --connection "ntrip://user:pass@caster-a.com:2101/MOUNT1" --active 1

python scripts/add_mountpoint.py --name "CASTER_B_MP2" \
  --connection "ntrip://user:pass@caster-b.com:2101/MOUNT2" --active 1

python scripts/add_mountpoint.py --name "LOCAL_TCP" \
  --connection "tcp://192.168.1.50:3000" --active 1

# Start hub (manages all connections in parallel)
python run.py
```

**MQTT Topics**:
- `s2d/osr/MOUNT1`
- `s2d/osr/MOUNT2`
- `s2d/osr/LOCAL_TCP` (uses name if no path in TCP URL)

---

### Example 3: Dynamic Mountpoint Management

```bash
# List all mountpoints
python scripts/list_mountpoints.py

# Disable a mountpoint (stops connection without deleting)
python scripts/set_mountpoint_active.py --id 1 --active 0

# Re-enable mountpoint
python scripts/set_mountpoint_active.py --id 1 --active 1
```

The hub automatically detects database changes and adjusts connections.

---

### Example 4: Consuming Data with Custom Script

**Python MQTT Subscriber** (`consumer.py`):

```python
import paho.mqtt.client as mqtt

def on_message(client, userdata, message):
    print(f"Received {len(message.payload)} bytes from {message.topic}")
    # Process RTCM data here (e.g., pass to RTK engine)

client = mqtt.Client()
client.username_pw_set("username", "password")
client.on_message = on_message
client.connect("localhost", 1883)
client.subscribe("s2d/osr/#")
client.loop_forever()
```

**Bash Subscriber** (using `mosquitto_sub`):

```bash
mosquitto_sub -h localhost -u username -P password -t "s2d/osr/MOUNT1" | \
  hexdump -C  # Display raw bytes
```

---

### Example 5: Using Legacy Scripts

For backward compatibility, the project includes standalone scripts:

**Publish NTRIP to MQTT**:
```bash
# Edit scripts/pub_data.sh with your settings
./scripts/pub_data.sh
```

**Subscribe and Process**:
```bash
# Edit scripts/sub_data.sh with your settings
./scripts/sub_data.sh
```

These scripts use `str2str` from RTKLIB for data handling.

---

## Monitoring

### Prometheus Metrics

TR-M2T exposes metrics at `http://localhost:8000/metrics`:

```prometheus
# Stream status (1 = connected, 0 = disconnected)
trm2t_stream_status{mountpoint="MOUNT1"} 1

# Bytes transferred
trm2t_bytes_transferred_total{mountpoint="MOUNT1",direction="received"} 1048576
```

**Example Grafana Dashboard**:
- Panel 1: Stream status over time (line graph)
- Panel 2: Bytes received per mountpoint (counter)
- Panel 3: Connection uptime (duration)

### Logs

Set `LOG_LEVEL=DEBUG` in `.env` for detailed logs:

```
2026-01-21 18:00:00 - trm2t.connection - DEBUG - Sending NTRIP request to caster.example.com:2101
2026-01-21 18:00:01 - trm2t.connection - INFO - Received ICY 200 OK from /MOUNT1
2026-01-21 18:00:01 - trm2t.worker - DEBUG - Published 1024 bytes to s2d/osr/MOUNT1
```

---

## Advanced Features

### RTCM Parsing

Enable RTCM message parsing to validate data:

```bash
# In .env
TRM2T_PARSE_RAW=true
```

When enabled, workers use `pyrtcm.RTCMReader` to parse messages, logging message types and detecting errors.

### Systemd Service

Run TR-M2T as a system service:

```bash
# Copy service file
sudo cp systemd/ntrip-mqtt-hub.service /etc/systemd/system/

# Edit paths in service file
sudo nano /etc/systemd/system/ntrip-mqtt-hub.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable ntrip-mqtt-hub
sudo systemctl start ntrip-mqtt-hub

# Check status
sudo systemctl status ntrip-mqtt-hub
```

### High Availability

For production deployments:
1. **Run multiple hubs** with different mountpoint sets
2. **Use MQTT QoS 1** for reliable delivery
3. **Monitor Prometheus metrics** and set up alerts
4. **Database replication** for shared mountpoint configuration

---

## Running the Application

The main application can be started using the `run.py` script. Ensure you have all dependencies installed (preferably in a virtual environment).

```bash
python run.py
```

This will start the core `trm2t` hub, which manages connections and data transformation.

For specific data publishing and subscribing examples, you can also use the legacy scripts in the `scripts/` directory:

*   `scripts/pub_data.sh`: Publishes example data using RTKLIB's str2str.
*   `scripts/sub_data.sh`: Subscribes to example data and processes it.

Further descriptions and usage instructions can be found in the repository's [Wiki](https://github.com/a5bru/TR-M2T/wiki).

---

## Troubleshooting

### Connection Errors

**"No Data available"** error:
- Check NTRIP credentials (username/password)
- Verify mountpoint path is correct (case-sensitive)
- Ensure NTRIP caster is reachable (`telnet caster.host 2101`)
- Check firewall rules

**MQTT connection failures**:
- Verify MQTT broker is running: `sudo systemctl status mosquitto`
- Test MQTT connection: `mosquitto_pub -h localhost -t test -m "hello"`
- Check MQTT credentials in `.env`

### Database Issues

**"Database locked"** error:
- Ensure only one hub instance is running
- Check file permissions on `mountpoints.db`

**Mountpoints not appearing**:
- Verify database location: `echo $TRM2T_DATABASE`
- List mountpoints: `python scripts/list_mountpoints.py`
- Check `active` flag is set to 1

### Performance Tuning

**High CPU usage**:
- Reduce `MQTT_HUB_WORKERS` (default: 2)
- Increase `ZMQ_PULL_PORT` buffer (system tuning)
- Disable RTCM parsing: `TRM2T_PARSE_RAW=false`

**Connection delays**:
- Increase `HUB_CREATION_LOADERS` for faster parallel connection creation
- Reduce `timeout` value for individual mountpoints

---

## Project Structure

```
TR-M2T/
├── src/trm2t/           # Main application code
│   ├── __init__.py
│   ├── __version__.py
│   ├── config.py        # Environment variable configuration
│   ├── hub.py           # Main hub (connection manager, event loop)
│   ├── connection.py    # TCP/NTRIP connection handling
│   ├── worker.py        # MQTT worker threads (ZMQ → MQTT)
│   ├── db.py            # Database operations
│   ├── metrics.py       # Prometheus metrics exporters
│   ├── m2t.py           # MQTT-to-TCP bridge (optional)
│   ├── n2m.py           # NTRIP-to-MQTT bridge (optional)
│   └── prom_config.py   # Prometheus configuration
├── scripts/             # Utility scripts
│   ├── init_db.py       # Initialize database
│   ├── add_mountpoint.py
│   ├── set_mountpoint_active.py
│   ├── list_mountpoints.py
│   ├── pub_data.sh      # Legacy RTKLIB publisher
│   └── sub_data.sh      # Legacy RTKLIB subscriber
├── tests/               # Unit tests
│   ├── test_config.py
│   ├── test_connection.py
│   ├── test_db.py
│   └── test_worker.py
├── docs/                # Documentation
│   ├── connection_hub.md
│   └── scripts.md
├── systemd/             # Systemd service files
│   └── ntrip-mqtt-hub.service
├── run.py               # Main entry point
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Project metadata
└── README.md            # This file
```

---

## API Reference

### Database Functions

```python
from trm2t.db import fetch_active_mountpoints, update_mountpoint

# Get all active mountpoints
mountpoints = fetch_active_mountpoints()  # [(id, connection_string, name, timeout), ...]

# Update mountpoint status
update_mountpoint(id=1, active=0)  # Disable mountpoint
update_mountpoint(id=1, name="NEW_NAME")  # Rename
```

### Connection Management

```python
from trm2t.connection import create_tcp_client

# Create NTRIP connection
socket = create_tcp_client("ntrip://user:pass@host:2101/MOUNT", timeout=15)

# Create raw TCP connection
socket = create_tcp_client("tcp://192.168.1.100:5000", timeout=10)
```

### Worker Configuration

Workers are automatically created by the hub. Configuration via environment variables:
- `MQTT_HUB_WORKERS`: Number of parallel workers
- `MQTT_TOPIC_PREFIX`: Base topic path
- `TRM2T_PARSE_RAW`: Enable RTCM parsing

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/my-feature`
3. **Commit** changes: `git commit -am 'Add new feature'`
4. **Push** to branch: `git push origin feature/my-feature`
5. **Submit** a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements.txt
pip install -e ".[dev]"  # Installs pytest, black, mypy, etc.

# Run tests
pytest

# Format code
black src/ tests/

# Type checking
mypy src/
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

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
