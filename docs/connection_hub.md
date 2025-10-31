# connection_hub.py Documentation

## Overview

`connection_hub.py` is the main hub script for managing NTRIP/TCP mountpoint connections and relaying data to MQTT. It handles:
- Managing active/inactive mountpoints from a SQLite database
- Creating and monitoring TCP/NTRIP client connections
- Relaying data from mountpoints to MQTT topics
- Handling connection robustness and reconnection logic
- Parallel mountpoint creation for scalability

## Main Components

### 1. Database Interaction
- Uses a SQLite database (default: `mountpoints.db`) to store mountpoint info.
- Functions: `fetch_active_mountpoints`, `update_mountpoint`, etc.

### 2. Connection Management
- `creation_thread`: Opens a TCP/NTRIP connection for a mountpoint.
- `check_mountpoints`: Periodically checks the database for active mountpoints, starts new connections in parallel, and disables inactive ones.
- Uses a thread pool for parallel connection creation (configurable via `HUB_CREATION_LOADERS`).

### 3. Data Handling
- Uses ZeroMQ for inter-thread communication.
- `handle_events`: Handles socket events and relays data to worker threads.
- `worker`: Publishes received data to MQTT topics, with robust reconnect logic.

### 4. MQTT Publishing
- Each worker thread runs an MQTT client.
- Handles reconnection and publish errors.
- Publishes data to topics based on mountpoint path.

### 5. Environment Variables
- `MQTT_HUB_WORKERS`: Number of MQTT worker threads
- `ZMQ_PULL_PORT`: Port for ZeroMQ communication
- `HUB_MAX_INACTIVE_COUNT`: Max retries before disabling a mountpoint
- `TRM2T_DATABSE`: Path to SQLite database
- `TRM2T_PARSE_RAW`: Enable/disable RTCM parsing
- `HUB_CREATION_LOADERS`: Number of parallel mountpoint creation threads
- MQTT connection details: `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PSWD`

## Usage

Run the hub:
```
python src/trm2t/connection_hub.py
```

## Notes
- Requires the database to be initialized and mountpoints to be present.
- Uses environment variables for configuration (see above).
- Designed for robustness and scalability in high-connection environments.

## See Also
- `docs/scripts.md` for utility scripts
- `README.md` for project overview
