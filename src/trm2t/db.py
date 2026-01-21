"""
Database module for managing NTRIP mountpoints.

This module provides functions to interact with the SQLite database
for managing NTRIP mountpoint configurations and their active status.
"""

import sqlite3
from typing import List, Optional, Tuple
from . import config


def update_mountpoint(
    id: int,
    name: Optional[str] = None,
    connection_string: Optional[str] = None,
    active: Optional[int] = None,
) -> None:
    """
    Update a mountpoint record in the database.

    Args:
        id: The mountpoint ID to update.
        name: Optional new name for the mountpoint.
        connection_string: Optional new connection string (e.g., ntrip://...).
        active: Optional active status (1 for active, 0 for inactive).

    Returns:
        None
    """
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()
    update_fields = []
    params = []

    if name is not None:
        update_fields.append("name = ?")
        params.append(name)
    if connection_string is not None:
        update_fields.append("connection_string = ?")
        params.append(connection_string)
    if active is not None:
        update_fields.append("active = ?")
        params.append(active)

    if update_fields:
        params.append(id)
        cursor.execute(
            f"""
            UPDATE mountpoints
            SET {', '.join(update_fields)}
            WHERE id = ?
        """,
            params,
        )
        conn.commit()
    conn.close()


def fetch_active_mountpoints() -> List[Tuple[int, str, str, int]]:
    """
    Fetch all active mountpoints from the database.

    Returns:
        A list of tuples containing (id, connection_string, name, timeout) for each active mountpoint.
    """
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, connection_string, name, timeout FROM mountpoints WHERE active = 1"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
