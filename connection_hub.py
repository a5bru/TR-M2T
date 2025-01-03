import sys
import sqlite3
import zmq
import socket
import select
import selectors
import time
import threading
import base64
import threading
import string
import os
import queue
import random
import paho.mqtt.client as mqtt

from urllib.parse import urlparse

WORKERS = int(os.environ.get("MQTT_HUB_WORKERS", "2"))
ZMQ_PULL_PORT = int(os.environ.get("ZMQ_PULL_PORT", "6969"))
MAX_INACTIVE_COUNT = int(os.environ.get("HUB_MAX_INACTIVE_COUNT", "10"))

context = zmq.Context()
selector = selectors.DefaultSelector()
connections = {}
inactive = {}


class DataConnection:
    def __init__(self, idx: int, url: str, socket: socket.socket, active: bool = True):
        self.idx = idx
        self.url = url
        self.active = active
        self.socket = socket
        self.inactive_count = 0


def update_mountpoint(id, name=None, connection_string=None, active=None):
    conn = sqlite3.connect('mountpoints.db')
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


def generate_random_string(length: int):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string


def create_tcp_client(url: str):

    # Parse url info
    o = urlparse(url)
    host = o.hostname
    port = o.port
    path = o.path
    auth = base64.b64encode(f"{o.username}:{o.password}".encode()).decode()

    # Create a TCP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (host, port)
    seconds = 1.0 

    try:
        client_socket.connect(server_address)

        request = f"GET {path} HTTP/1.0\r\n"
        request += "User-Agent: Ntrip N2Mqtt/v0.1\r\n"
        request += "Connection: close\r\n"
        request += f"Host: {host}\r\n"
        request += f"Authorization: Basic {auth}\r\n"
        request += "\r\n"
        client_socket.sendall(request.encode()) 
        readable, _, _ = select.select([client_socket, ], [], [], seconds)
        if not readable:
            assert False, f"E: {path}: No Response within {seconds} sec(s)."
        data = client_socket.recv(1024)
        
        # make sure request was not denied
        assert not data.startswith(b"HTTP"), f"E: {path}: Response Error {data[:20].decode()}.."
        # make sure mountpoint is alive
        assert b"SOURCETABLE" not in data, f"E: {path}: No Data availale"
        # catch all non-200 responses
        assert data.startswith(b"ICY 200 OK"), f"E: {path}: No Ntrip Response"

    except AssertionError as e:
        print(e, file=sys.stderr)
        return None

    except Exception as e:
        print(e)
        return None

    return client_socket


def fetch_active_mountpoints():
    conn = sqlite3.connect('mountpoints.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, connection_string FROM mountpoints WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    return rows


def creation_thread(id: int, connection_string: str):
    o = urlparse(connection_string)
    print(f"I: {o.path}: Opening connection")
    conn = create_tcp_client(connection_string)
    if conn is not None:
        fd = conn.fileno()
        selector.register(conn, selectors.EVENT_READ)
        connections[fd] = DataConnection(idx=id, url=connection_string, socket=conn, active=True) 
        if o.path in inactive_count:
            inactive_count.pop(o.path)
    else:
        if o.path not in inactive_count:
            inactive_count[o.path] = 0

        inactive_count[o.path] += 1

        if inactive_count[o.path] > MAX_INACTIVE_COUNT:
            # TODO disable mountpoint
            update_mountpoint(id, active=False)
 


def check_mountpoints(sock):

    while True:

        print("Check for active mountpoints")
        active_mountpoints = fetch_active_mountpoints()
        active_ids = set(mp[0] for mp in active_mountpoints)

        # shut down active stream
        for fd in list(connections.keys()):
            if connections[fd].idx not in active_ids:
                o = urlparse(connections[fd].url)
                print(f"I: {o.path}: Closing connection")
                sock.sendall(f"{fd}:".encode())

        # active stream
        active_streams = []

        for fd in list(connections.keys()):
            active_streams.append(connections[fd].idx)

        for id, connection_string in active_mountpoints:
            if id not in active_streams:
                creation_thread(id, connection_string)

        time.sleep(10)


def handle_events(sock):

    sender = context.socket(zmq.PUSH)
    sender.bind(f"tcp://*:{ZMQ_PULL_PORT}")
    selector.register(sock, selectors.EVENT_READ)

    while True:

        events = selector.select(timeout=None)

        for key, mask in events:
            conn = key.fileobj
            data = conn.recv(1024)

            if conn == sock:
                # remove a connection
                for fd_b in sock.recv(1024).split(b":"):
                    fd = int(fd_b)
                    if fd in connections:
                        selector.unregister(connections[fd].socket)
                        connections[fd].active = False
                        connections[fd].socket.close()
                        del connections[fd]

            else:
                fd = conn.fileno()
                if data:
                    sender.send_pyobj((fd, data))
                else:
                    selector.unregister(conn)
                    conn.close()
                    if fd in connections:
                        connections[fd].active = False
                        del connections[fd]

        time.sleep(0.0001)


def worker(w_id: int, url: str):

    receiver = context.socket(zmq.PULL)
    receiver.connect(f"tcp://localhost:{ZMQ_PULL_PORT}")

    o = urlparse(url)

    # Initialize MQTT Client
    mqtt_client_id = f"n2m-{w_id:02d}-{generate_random_string(8)}"
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id)
    if o.username and o.password:
        mqtt_client.username_pw_set(o.username, o.password)
    
    mqtt_client.connect(o.hostname, o.port)

    keep_running = True
    next_beat = time.time()
    mqtt_client.loop_start()  # Start the MQTT client loop

    print(f"Started MQTT client {mqtt_client_id}")

    while True:

        fd, data = receiver.recv_pyobj()

        if fd in list(connections.keys()):
            try:
                url = connections[fd].url
                o2 = urlparse(url)
                p2 = o2.path[1:]

                topic = f"s2d/osr/{p2}/rtcm"
                if len(data) > 0:
                    # Publish received data to MQTT
                    mqtt_client.publish(topic, data)

            except Exception as e:
                print(e)

        time.sleep(0.000000001)

    mqtt_client.loop_stop()  # Stop the MQTT client loop


def main():

    sock1, sock2 = socket.socketpair()

    # start worker threads
    MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
    MQTT_PORT = os.environ.get("MQTT_PORT", "1883")
    MQTT_USER = os.environ.get("MQTT_USER", "user")
    MQTT_PSWD = os.environ.get("MQTT_USER", "pswd")
    mqtt_url = f"mqtt://{MQTT_USER}:{MQTT_PSWD}@{MQTT_HOST}:{MQTT_PORT}"
    for i in range(WORKERS):
        t = threading.Thread(target=worker, args=(i, mqtt_url))
        t.daemon = True
        t.start()
    time.sleep(3)

    # start checker thread
    db_thread = threading.Thread(target=check_mountpoints, args=(sock1,))
    db_thread.daemon = True
    db_thread.start()

    # start selector
    handle_events(sock2)


if __name__ == "__main__":
    main()

