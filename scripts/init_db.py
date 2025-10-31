import sqlite3
import os

DB_PATH = os.environ.get("TRM2T_DATABSE", "mountpoints.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mountpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            connection_string TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            timeout INTEGER NOT NULL DEFAULT 15
        )
    """
    )
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
