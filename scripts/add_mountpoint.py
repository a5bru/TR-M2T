import sqlite3
import argparse
import os

# Use the same env var as the app
DB_PATH = os.environ.get("TRM2T_DATABASE", "mountpoints.db")


def add_mountpoint(name, connection_string, active=1, timeout=15):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO mountpoints (name, connection_string, active, timeout)
        VALUES (?, ?, ?, ?)
    """,
        (name, connection_string, int(active), int(timeout)),
    )
    conn.commit()
    conn.close()
    print(f"Added mountpoint: {name} (timeout={timeout}s)")


def main():
    parser = argparse.ArgumentParser(description="Add a mountpoint to the database.")
    parser.add_argument("--name", required=True, help="Name of the mountpoint")
    parser.add_argument(
        "--connection",
        required=True,
        help="Connection string (e.g. ntrip://user:pass@host:port/mount)",
    )
    parser.add_argument("--active", type=int, default=1, help="Active flag (1=active, 0=inactive)")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout in seconds for the stream")
    args = parser.parse_args()
    add_mountpoint(args.name, args.connection, args.active, args.timeout)


if __name__ == "__main__":
    main()
