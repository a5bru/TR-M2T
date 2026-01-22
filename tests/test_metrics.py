"""Tests for metrics module."""

import pytest
from prometheus_client import REGISTRY


def test_metrics_exist():
    """Test that metrics are properly defined."""
    from trm2t.metrics import STREAM_STATUS, BYTES_TRANSFERRED

    assert STREAM_STATUS is not None
    assert BYTES_TRANSFERRED is not None


def test_stream_status_gauge():
    """Test STREAM_STATUS gauge metric."""
    from trm2t.metrics import STREAM_STATUS

    # Set status for a test mountpoint
    STREAM_STATUS.labels(mountpoint="TEST_MOUNT").set(1)
    value = STREAM_STATUS.labels(mountpoint="TEST_MOUNT")._value.get()
    assert value == 1

    # Change status
    STREAM_STATUS.labels(mountpoint="TEST_MOUNT").set(0)
    value = STREAM_STATUS.labels(mountpoint="TEST_MOUNT")._value.get()
    assert value == 0


def test_bytes_transferred_counter():
    """Test BYTES_TRANSFERRED counter metric."""
    from trm2t.metrics import BYTES_TRANSFERRED

    # Get initial value
    initial = BYTES_TRANSFERRED.labels(mountpoint="TEST_MOUNT2")._value.get()

    # Increment counter
    BYTES_TRANSFERRED.labels(mountpoint="TEST_MOUNT2").inc(1024)

    # Check value increased
    new_value = BYTES_TRANSFERRED.labels(mountpoint="TEST_MOUNT2")._value.get()
    assert new_value == initial + 1024


def test_bytes_transferred_counter_multiple_increments():
    """Test BYTES_TRANSFERRED with multiple increments."""
    from trm2t.metrics import BYTES_TRANSFERRED

    mountpoint = "TEST_MOUNT3"
    initial = BYTES_TRANSFERRED.labels(mountpoint=mountpoint)._value.get()

    # Multiple increments
    BYTES_TRANSFERRED.labels(mountpoint=mountpoint).inc(100)
    BYTES_TRANSFERRED.labels(mountpoint=mountpoint).inc(200)
    BYTES_TRANSFERRED.labels(mountpoint=mountpoint).inc(300)

    final = BYTES_TRANSFERRED.labels(mountpoint=mountpoint)._value.get()
    assert final == initial + 600


def test_metrics_registered():
    """Test that metrics are registered with Prometheus."""
    from trm2t.metrics import STREAM_STATUS, BYTES_TRANSFERRED

    # Get all registered metric names
    metric_names = []
    for collector in REGISTRY.collect():
        for metric in collector.samples:
            metric_names.append(metric.name)

    # Check that our metrics are in the list
    assert any("stream_status" in name for name in metric_names)
    assert any("stream_bytes_transferred" in name for name in metric_names)


def test_metrics_labels():
    """Test that metrics support proper labels."""
    from trm2t.metrics import STREAM_STATUS, BYTES_TRANSFERRED

    # Test different mountpoint labels
    STREAM_STATUS.labels(mountpoint="MOUNT_A").set(1)
    STREAM_STATUS.labels(mountpoint="MOUNT_B").set(0)

    # Values should be independent
    assert STREAM_STATUS.labels(mountpoint="MOUNT_A")._value.get() == 1
    assert STREAM_STATUS.labels(mountpoint="MOUNT_B")._value.get() == 0

    # Same for counter
    BYTES_TRANSFERRED.labels(mountpoint="MOUNT_A").inc(1000)
    BYTES_TRANSFERRED.labels(mountpoint="MOUNT_B").inc(2000)

    # Check both counters have different values
    a_value = BYTES_TRANSFERRED.labels(mountpoint="MOUNT_A")._value.get()
    b_value = BYTES_TRANSFERRED.labels(mountpoint="MOUNT_B")._value.get()
    assert a_value != b_value
