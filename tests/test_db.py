"""Tests for database module."""

import sqlite3
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Patch config to use temp database
    from trm2t import config

    monkeypatch.setattr(config, "DATABASE", db_path)

    # Initialize database schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mountpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            connection_string TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            timeout INTEGER DEFAULT 15
        )
    """
    )
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def test_fetch_active_mountpoints_empty(temp_db):
    """Test fetching active mountpoints from empty database."""
    from trm2t.db import fetch_active_mountpoints

    result = fetch_active_mountpoints()
    assert result == []


def test_fetch_active_mountpoints(temp_db):
    """Test fetching active mountpoints."""
    from trm2t.db import fetch_active_mountpoints

    # Insert test data
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mountpoints (name, connection_string, active, timeout) VALUES (?, ?, ?, ?)",
        ("test_mount", "ntrip://user:pass@host:2101/MOUNT1", 1, 30),
    )
    cursor.execute(
        "INSERT INTO mountpoints (name, connection_string, active, timeout) VALUES (?, ?, ?, ?)",
        ("inactive_mount", "ntrip://user:pass@host:2101/MOUNT2", 0, 30),
    )
    conn.commit()
    conn.close()

    result = fetch_active_mountpoints()
    assert len(result) == 1
    assert result[0][1] == "ntrip://user:pass@host:2101/MOUNT1"
    assert result[0][2] == 30


def test_update_mountpoint_name(temp_db):
    """Test updating mountpoint name."""
    from trm2t.db import update_mountpoint, fetch_active_mountpoints

    # Insert test data
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mountpoints (name, connection_string, active) VALUES (?, ?, ?)",
        ("old_name", "ntrip://user:pass@host:2101/MOUNT1", 1),
    )
    mp_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Update the name
    update_mountpoint(mp_id, name="new_name")

    # Verify update
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM mountpoints WHERE id = ?", (mp_id,))
    result = cursor.fetchone()
    conn.close()

    assert result[0] == "new_name"


def test_update_mountpoint_active_status(temp_db):
    """Test updating mountpoint active status."""
    from trm2t.db import update_mountpoint

    # Insert test data
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mountpoints (name, connection_string, active) VALUES (?, ?, ?)",
        ("test", "ntrip://user:pass@host:2101/MOUNT1", 1),
    )
    mp_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Update active status
    update_mountpoint(mp_id, active=0)

    # Verify update
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT active FROM mountpoints WHERE id = ?", (mp_id,))
    result = cursor.fetchone()
    conn.close()

    assert result[0] == 0


def test_update_mountpoint_connection_string(temp_db):
    """Test updating mountpoint connection string."""
    from trm2t.db import update_mountpoint

    # Insert test data
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mountpoints (name, connection_string, active) VALUES (?, ?, ?)",
        ("test", "ntrip://user:pass@host:2101/MOUNT1", 1),
    )
    mp_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Update connection string
    new_conn = "ntrip://user:pass@newhost:2101/MOUNT2"
    update_mountpoint(mp_id, connection_string=new_conn)

    # Verify update
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT connection_string FROM mountpoints WHERE id = ?", (mp_id,))
    result = cursor.fetchone()
    conn.close()

    assert result[0] == new_conn


def test_update_mountpoint_multiple_fields(temp_db):
    """Test updating multiple mountpoint fields at once."""
    from trm2t.db import update_mountpoint

    # Insert test data
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mountpoints (name, connection_string, active) VALUES (?, ?, ?)",
        ("old", "ntrip://user:pass@host:2101/OLD", 1),
    )
    mp_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Update multiple fields
    update_mountpoint(
        mp_id, name="new", connection_string="ntrip://user:pass@host:2101/NEW", active=0
    )

    # Verify updates
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name, connection_string, active FROM mountpoints WHERE id = ?", (mp_id,))
    result = cursor.fetchone()
    conn.close()

    assert result[0] == "new"
    assert result[1] == "ntrip://user:pass@host:2101/NEW"
    assert result[2] == 0
