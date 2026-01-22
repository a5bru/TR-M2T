#!/usr/bin/env python3
import argparse
import os
import sqlite3
import sys

DB_PATH = os.environ.get("TRM2T_DATABASE", "mountpoints.db")


def list_mountpoints(show_inactive: bool = True):
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, connection_string, active, timeout FROM mountpoints"
    params = []
    if not show_inactive:
        query += " WHERE active = 1"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No mountpoints found.")
        return 0

    print(f"Mountpoints in {DB_PATH} (active only: {not show_inactive}):")
    for rid, name, conn_str, active, timeout in rows:
        status = "enabled" if active else "disabled"
        print(f"- id={rid} name={name} status={status:<8s} timeout={timeout}s conn={conn_str}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="List mountpoints in the database")
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Show only active mountpoints",
    )
    args = parser.parse_args()
    sys.exit(list_mountpoints(show_inactive=not args.active_only))


if __name__ == "__main__":
    main()
