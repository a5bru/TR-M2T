"""Tests for configuration module."""

import os
import pytest


def test_config_defaults():
    """Test that config module loads with default values."""
    from trm2t import config

    assert config.RECV_BUFFER_SIZE > 0
    assert config.WORKERS > 0
    assert config.ZMQ_PULL_PORT > 0
    assert config.MQTT_HOST is not None
    assert config.MQTT_PORT > 0
    assert config.PROM_PORT > 0
    assert config.USER_AGENT is not None


def test_config_database_path():
    """Test that database path is configured."""
    from trm2t import config

    assert config.DATABASE is not None
    assert isinstance(config.DATABASE, str)
    assert len(config.DATABASE) > 0


def test_config_environment_override(monkeypatch):
    """Test that environment variables override defaults."""
    monkeypatch.setenv("RECV_BUFFER_SIZE", "8192")
    monkeypatch.setenv("MQTT_HOST", "test.mqtt.local")
    monkeypatch.setenv("MQTT_PORT", "1234")

    # Reload config to pick up new env vars
    import importlib
    from trm2t import config as config_module

    importlib.reload(config_module)

    assert config_module.RECV_BUFFER_SIZE == 8192
    assert config_module.MQTT_HOST == "test.mqtt.local"
    assert config_module.MQTT_PORT == 1234


def test_config_user_agent_format():
    """Test that user agent string is properly formatted."""
    from trm2t import config

    assert "Ntrip N2Mqtt" in config.USER_AGENT
    assert "/" in config.USER_AGENT
    assert "v" in config.USER_AGENT
