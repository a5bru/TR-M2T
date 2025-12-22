import sqlite3
from . import config


def update_mountpoint(id, name=None, connection_string=None, active=None):
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


def fetch_active_mountpoints():
    conn = sqlite3.connect(config.DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, connection_string, timeout FROM mountpoints WHERE active = 1"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
