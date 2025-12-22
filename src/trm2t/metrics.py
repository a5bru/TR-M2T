from prometheus_client import Counter, Gauge

# Metrics
STREAM_STATUS = Gauge('stream_status', 'Connection status of the stream (1=online, 0=offline)', ['mountpoint'])
BYTES_TRANSFERRED = Counter('stream_bytes_transferred_total', 'Total bytes transferred', ['mountpoint'])
