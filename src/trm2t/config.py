"""
Configuration module for TR-M2T (NTRIP to MQTT hub).

This module loads environment variables and provides centralized configuration
constants for the application including database, MQTT, hub, worker, and
Prometheus settings.
"""

import os
import logging
from dotenv import load_dotenv
from .__version__ import __version__

load_dotenv()

# Logging
LOG_LEVEL = os.environ.get("TRM2T_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# General
RECV_BUFFER_SIZE = int(os.environ.get("RECV_BUFFER_SIZE", 1024 * 8))

# Database
DATABASE = os.environ.get("TRM2T_DATABASE", "mountpoints.db")

# Hub
WORKERS = int(os.environ.get("MQTT_HUB_WORKERS", "2"))
ZMQ_PULL_PORT = int(os.environ.get("ZMQ_PULL_PORT", "6969"))
ZMQ_HWM = int(os.environ.get("ZMQ_HWM", "10000"))  # ZMQ High Water Mark
HUB_MAX_INACTIVE_COUNT = int(os.environ.get("HUB_MAX_INACTIVE_COUNT", "10"))
HUB_CREATION_LOADERS = int(os.environ.get("HUB_CREATION_LOADERS", "8"))

# Worker
MQTT_TOPIC_PREFIX = os.environ.get("MQTT_PATH", "s2d/osr")
PARSE_RAW = (
    True
    if os.environ.get("TRM2T_PARSE_RAW", "false").strip().lower() in ["yes", "true", "1"]
    else False
)

# MQTT
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "user")
MQTT_PSWD = os.environ.get("MQTT_PSWD", "pswd")

# Prometheus
PROM_PORT = int(os.environ.get("PROM_PORT", "8000"))

# Versioning / User-Agent
VERSION = os.environ.get("TRM2T_VERSION", __version__)
USER_AGENT = f"Ntrip N2Mqtt/v{VERSION}"
