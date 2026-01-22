"""Tests for connection module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import socket
from trm2t.connection import DataConnection, create_tcp_client


def test_data_connection_creation():
    """Test DataConnection object creation."""
    mock_socket = Mock(spec=socket.socket)
    conn = DataConnection(
        1, "ntrip://user:pass@host:2101/MOUNT1", mock_socket, name="MOUNT1", timeout=15, active=True
    )

    assert conn.idx == 1
    assert conn.url == "ntrip://user:pass@host:2101/MOUNT1"
    assert conn.name == "MOUNT1"
    assert conn.timeout == 15
    assert conn.active is True
    assert conn.socket == mock_socket
    assert conn._buffer is not None


def test_data_connection_default_active():
    """Test DataConnection default active state."""
    mock_socket = Mock(spec=socket.socket)
    conn = DataConnection(1, "ntrip://user:pass@host:2101/MOUNT1", mock_socket)

    assert conn.active is True
    assert conn.name == ""
    assert conn.timeout == 15


@patch("socket.socket")
def test_create_tcp_client_timeout(mock_socket_class):
    """Test TCP client creation with timeout."""
    # Mock socket instance
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance
    mock_socket_instance.connect.side_effect = socket.timeout("Connection timeout")

    result = create_tcp_client("tcp://host:1234/path", timeout=5)

    assert result is None
    mock_socket_instance.settimeout.assert_called_with(5)


@patch("socket.socket")
def test_create_tcp_client_connection_refused(mock_socket_class):
    """Test TCP client when connection is refused."""
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance
    mock_socket_instance.connect.side_effect = ConnectionRefusedError("Connection refused")

    result = create_tcp_client("tcp://host:1234/path")

    assert result is None


@patch("socket.socket")
@patch("select.select")
def test_create_tcp_client_ntrip_success(mock_select, mock_socket_class):
    """Test successful NTRIP connection."""
    # Mock socket instance
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance

    # Mock successful connection
    mock_socket_instance.connect.return_value = None

    # Mock select to indicate socket is readable
    mock_select.return_value = ([mock_socket_instance], [], [])

    # Mock recv to return valid NTRIP response
    mock_socket_instance.recv.return_value = b"ICY 200 OK\r\n"

    result = create_tcp_client("ntrip://user:pass@host:2101/MOUNT1")

    assert result == mock_socket_instance
    mock_socket_instance.connect.assert_called_once()
    mock_socket_instance.sendall.assert_called_once()


@patch("socket.socket")
@patch("select.select")
def test_create_tcp_client_ntrip_no_data(mock_select, mock_socket_class):
    """Test NTRIP connection when no data is available."""
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance
    mock_socket_instance.connect.return_value = None
    mock_select.return_value = ([mock_socket_instance], [], [])
    mock_socket_instance.recv.return_value = b"SOURCETABLE 200 OK\r\n"

    result = create_tcp_client("ntrip://user:pass@host:2101/MOUNT1")

    assert result is None


@patch("socket.socket")
@patch("select.select")
def test_create_tcp_client_ntrip_http_error(mock_select, mock_socket_class):
    """Test NTRIP connection with HTTP error response."""
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance
    mock_socket_instance.connect.return_value = None
    mock_select.return_value = ([mock_socket_instance], [], [])
    mock_socket_instance.recv.return_value = b"HTTP/1.1 401 Unauthorized\r\n"

    result = create_tcp_client("ntrip://user:pass@host:2101/MOUNT1")

    assert result is None


@patch("socket.socket")
def test_create_tcp_client_tcp_scheme(mock_socket_class):
    """Test simple TCP connection without NTRIP handshake."""
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance
    mock_socket_instance.connect.return_value = None

    result = create_tcp_client("tcp://host:1234/path")

    assert result == mock_socket_instance
    # Should not call sendall for TCP scheme (no handshake)
    mock_socket_instance.sendall.assert_not_called()


def test_create_tcp_client_invalid_scheme():
    """Test TCP client with unsupported scheme."""
    with patch("socket.socket") as mock_socket_class:
        mock_socket_instance = Mock()
        mock_socket_class.return_value = mock_socket_instance
        mock_socket_instance.connect.return_value = None

        result = create_tcp_client("http://host:80/path")

        assert result is None


@patch("socket.socket")
@patch("select.select")
def test_create_tcp_client_select_timeout(mock_select, mock_socket_class):
    """Test NTRIP connection when select times out."""
    mock_socket_instance = Mock()
    mock_socket_class.return_value = mock_socket_instance
    mock_socket_instance.connect.return_value = None

    # Mock select to return empty (no readable sockets = timeout)
    mock_select.return_value = ([], [], [])

    result = create_tcp_client("ntrip://user:pass@host:2101/MOUNT1")

    assert result is None
