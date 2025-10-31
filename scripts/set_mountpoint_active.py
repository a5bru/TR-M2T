import sqlite3
import argparse
import os


DB_PATH = os.environ.get("TRM2T_DATABSE", "mountpoints.db")


def get_mountpoint_names():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM mountpoints")
    names = [row[0] for row in cursor.fetchall()]
    conn.close()
    return names


def set_mountpoint_active(name, active):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE mountpoints SET active = ? WHERE name = ?
    """,
        (int(active), name),
    )
    conn.commit()
    conn.close()
    print(f"Mountpoint name '{name}' set to active={active}")


def main():
    parser = argparse.ArgumentParser(
        description="Enable or disable a mountpoint by name."
    )
    names = get_mountpoint_names()
    parser.add_argument(
        "--name",
        required=True,
        help="Mountpoint name (unique)",
        choices=names if names else None,
    )
    parser.add_argument(
        "--active",
        required=True,
        type=int,
        choices=[0, 1],
        help="Set to 1 to enable, 0 to disable",
    )
    args = parser.parse_args()
    set_mountpoint_active(args.name, args.active)


if __name__ == "__main__":
    main()
