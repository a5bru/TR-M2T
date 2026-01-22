"""
Prometheus metrics module for monitoring stream status and data transfer.

This module defines and exposes Prometheus metrics for tracking
connection status and data transfer statistics for NTRIP streams.
"""

from prometheus_client import Counter, Gauge

# Metrics
STREAM_STATUS: Gauge = Gauge(
    "stream_status", "Connection status of the stream (1=online, 0=offline)", ["mountpoint"]
)
BYTES_TRANSFERRED: Counter = Counter(
    "stream_bytes_transferred_total", "Total bytes transferred", ["mountpoint"]
)
