import sqlite3
import argparse
import os

DB_PATH = os.environ.get("TRM2T_DATABSE", "mountpoints.db")


def add_mountpoint(name, connection_string, active=1):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO mountpoints (name, connection_string, active)
        VALUES (?, ?, ?)
    """,
        (name, connection_string, int(active)),
    )
    conn.commit()
    conn.close()
    print(f"Added mountpoint: {name}")


def main():
    parser = argparse.ArgumentParser(description="Add a mountpoint to the database.")
    parser.add_argument("--name", required=True, help="Name of the mountpoint")
    parser.add_argument(
        "--connection",
        required=True,
        help="Connection string (e.g. ntrip://user:pass@host:port/mount)",
    )
    parser.add_argument(
        "--active", type=int, default=1, help="Active flag (1=active, 0=inactive)"
    )
    args = parser.parse_args()
    add_mountpoint(args.name, args.connection, args.active)


if __name__ == "__main__":
    main()
