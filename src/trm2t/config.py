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


def is_true(value: str) -> bool:
    """check if string seems to be true, return false if not."""
    return str(value).strip().lower() in ["yes", "true", "1"]


# Logging
LOG_LEVEL = os.environ.get("TRM2T_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(name)s - %(levelname)s - %(message)s",
)

# General
RECV_BUFFER_SIZE = int(os.environ.get("TRM2T_RECV_BUFFER_SIZE", 1024 * 8))

# Database
DATABASE = os.environ.get("TRM2T_DATABASE", "mountpoints.db")

# Hub
WORKERS = int(os.environ.get("TRM2T_MQTT_HUB_WORKERS", "2"))
ZMQ_PULL_PORT = int(os.environ.get("ZMQ_PULL_PORT", "6969"))
ZMQ_HWM = int(os.environ.get("ZMQ_HWM", "10000"))  # ZMQ High Water Mark
HUB_MAX_INACTIVE_COUNT = int(os.environ.get("HUB_MAX_INACTIVE_COUNT", "10"))
HUB_CREATION_LOADERS = int(os.environ.get("HUB_CREATION_LOADERS", "8"))

# Worker
MQTT_TOPIC_PREFIX = os.environ.get("TRM2T_MQTT_PATH", "s2d/osr")
PARSE_RAW = is_true(os.environ.get("TRM2T_PARSE_RAW", "false"))
PARSE_POOL_SIZE = int(os.environ.get("TRM2T_PARSE_POOL_SIZE", "2"))
MESSAGE_AGE = float(os.environ.get("TRM2T_MESSAGE_AGE", "1.5"))
MQTT_CLIENT_POOL_SIZE = int(os.environ.get("TRM2T_MQTT_CLIENT_POOL_SIZE", "1"))
MQTT_MAX_QUEUED_MESSAGES = int(os.environ.get("TRM2T_MQTT_MAX_QUEUED_MESSAGES", "0"))
MQTT_MAX_INFLIGHT = int(os.environ.get("TRM2T_MQTT_MAX_INFLIGHT", "20"))

# TCP relay (per-connection TCP servers)
TCP_RELAY_ENABLED = is_true(os.environ.get("TRM2T_TCP_RELAY", "true"))
TCP_RELAY_BASE_PORT = int(os.environ.get("TRM2T_TCP_RELAY_BASE_PORT", "24000"))
TCP_RELAY_BIND = os.environ.get("TRM2T_TCP_RELAY_BIND", "0.0.0.0")
TCP_RELAY_BACKLOG = int(os.environ.get("TRM2T_TCP_RELAY_BACKLOG", "8"))
TCP_RELAY_QUEUE = int(os.environ.get("TRM2T_TCP_RELAY_QUEUE", "5000"))

# MQTT
MQTT_HOST = os.environ.get("TRM2T_MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("TRM2T_MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("TRM2T_MQTT_USER", "user")
MQTT_PSWD = os.environ.get("TRM2T_MQTT_PSWD", "pswd")

# Prometheus
PROM_PORT = int(os.environ.get("TRM2T_PROM_PORT", "8000"))

# Versioning / User-Agent
VERSION = os.environ.get("TRM2T_VERSION", __version__)
USER_AGENT = f"Ntrip N2Mqtt/v{VERSION}"
