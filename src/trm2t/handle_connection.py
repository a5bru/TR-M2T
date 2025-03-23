import os
import sqlite3
import argparse

DATABASE = os.environ.get("TRM2T_DATABASE", "mountpoints.db")


def setup_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mountpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            connection_string TEXT NOT NULL,
            active BOOLEAN NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def insert_mountpoint(name, connection_string, active):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO mountpoints (name, connection_string, active) 
        VALUES (?, ?, ?)
    ''', (name, connection_string, active))
    conn.commit()
    conn.close()


def update_mountpoint(id, name=None, connection_string=None, active=None):
    conn = sqlite3.connect(DATABASE)
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
        cursor.execute(f'''
            UPDATE mountpoints 
            SET {', '.join(update_fields)} 
            WHERE id = ?
        ''', params)
        conn.commit()
    conn.close()


def delete_mountpoint(id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM mountpoints WHERE id = ?
    ''', (id,))
    conn.commit()
    conn.close()


def fetch_mountpoints():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM mountpoints
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows


parser = argparse.ArgumentParser()
parser.add_argument("name", type=str)
parser.add_argument("--url", type=str, default=os.environ.get("NTRIP_URL", ""))
parser.add_argument("--enable", action="store_true")


if __name__ == "__main__":
    setup_database()

    args = parser.parse_args()
    
    # Example usage
    if args.url:
        insert_mountpoint(args.name, f"{args.url}/{args.name}", args.enable)

    #for i in range(10, 20):
    #    update_mountpoint(i, active=True)
    for mp in fetch_mountpoints():
        update_mountpoint(mp[0], active=True)
