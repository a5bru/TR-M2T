import sys
import sqlite3
import socket
import select
import selectors
import string
import time
import base64
import threading
import traceback
import os
import queue
import random
import io

from urllib.parse import urlparse

import zmq
import paho.mqtt.client as mqtt
import setproctitle

from dotenv import load_dotenv

load_dotenv()

RECV_BUFFER_SIZE = 4096
WORKERS = int(os.environ.get("MQTT_HUB_WORKERS", "2"))
ZMQ_PULL_PORT = int(os.environ.get("ZMQ_PULL_PORT", "6969"))
MAX_INACTIVE_COUNT = int(os.environ.get("HUB_MAX_INACTIVE_COUNT", "10"))
DATABASE = os.environ.get("TRM2T_DATABSE", "mountpoints.db")
PARSE_RAW = os.environ.get("TRM2T_PARSE_RAW", False)

context = zmq.Context()
selector = selectors.DefaultSelector()
connections = {}
inactive = {}

run_event = threading.Event()

enable_queue = queue.Queue()


class DataConnection:
    def __init__(self, idx: int, url: str, socket: socket.socket, active: bool = True):
        self.idx = idx
        self.url = url
        self.active = active
        self.socket = socket
        self._buffer = io.BytesIO()


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


def generate_random_string(length: int):
    characters = string.ascii_letters + string.digits
    random_string = "".join(random.choice(characters) for _ in range(length))
    return random_string


def create_tcp_client(url: str, timeout: int = 15):

    # Parse url info
    o = urlparse(url)
    host = o.hostname
    port = o.port
    path = o.path
    auth = base64.b64encode(f"{o.username}:{o.password}".encode()).decode()

    # Create a TCP socket with reconnection attempts
    max_retries = 5
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            server_address = (host, port)
            seconds = 1.0
            client_socket.connect(server_address)

            if o.scheme.lower() == "ntrip":
                request = f"GET {path} HTTP/1.0\r\n"
                request += "User-Agent: Ntrip N2Mqtt/v0.1\r\n"
                request += "Connection: close\r\n"
                request += f"Host: {host}\r\n"
                request += f"Authorization: Basic {auth}\r\n"
                request += "\r\n"
                client_socket.sendall(request.encode())
                readable, _, _ = select.select(
                    [
                        client_socket,
                    ],
                    [],
                    [],
                    seconds,
                )
                if not readable:
                    raise TimeoutError(
                        f"E: {path}: No Response within {seconds} sec(s)."
                    )
                data = client_socket.recv(RECV_BUFFER_SIZE)
                # make sure request was not denied
                if data.startswith(b"HTTP"):
                    raise ConnectionError(
                        f"E: {path}: Response Error {data[:20].decode()}.."
                    )
                if b"SOURCETABLE" in data:
                    raise ConnectionError(f"E: {path}: No Data available")
                if not data.startswith(b"ICY 200 OK"):
                    raise ConnectionError(f"E: {path}: No Ntrip Response")
            elif o.scheme.lower() == "tcp":
                # simple TCP connection, no handshake
                pass
            else:
                raise ValueError(f"E: {path}: Unsupported scheme {o.scheme}")
            return client_socket
        except Exception as e:
            print(
                f"TCP connection error (attempt {attempt+1}/{max_retries}): {e}",
                file=sys.stderr,
            )
            try:
                client_socket.close()
            except Exception:
                pass
            time.sleep(retry_delay)
    print(
        f"Failed to connect to TCP server after {max_retries} attempts ({path}).",
        file=sys.stderr,
    )
    return None


def fetch_active_mountpoints():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, connection_string, timeout FROM mountpoints WHERE active = 1"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def creation_thread(id: int, connection_string: str, timeout: int = 15):
    o = urlparse(connection_string)
    print(f"I: {o.path}: Opening connection (fd={id})")
    conn = create_tcp_client(connection_string, timeout=timeout)
    if conn is not None:
        fd = conn.fileno()
        selector.register(conn, selectors.EVENT_READ)
        connections[fd] = DataConnection(
            idx=id, url=connection_string, socket=conn, active=True
        )
        if o.path in inactive:
            inactive.pop(o.path)
    else:
        if o.path not in inactive:
            inactive[o.path] = 0

        inactive[o.path] += 1

        if inactive[o.path] > MAX_INACTIVE_COUNT:
            # TODO disable mountpoint
            update_mountpoint(id, active=False)


def check_mountpoints(name: str, sock):

    setproctitle.setproctitle(name)
    print(f"Thread {name}")

    while not run_event.is_set():

        print("Check for active mountpoints")
        active_mountpoints = fetch_active_mountpoints()
        active_ids = set(mp[0] for mp in active_mountpoints)
        found_inactive = False

        # shut down active stream
        for fd in list(connections.keys()):
            if connections[fd].idx not in active_ids:
                enable_queue.put_nowait(int(fd))
                o = urlparse(connections[fd].url)
                print(f"I: {o.path}: Closing connection")
                found_inactive = True

        if found_inactive:
            sock.sendall(b"1")

        # active stream
        active_streams = []

        for fd in list(connections.keys()):
            active_streams.append(connections[fd].idx)

        # Parallelize mountpoint creation with multiple loader threads
        from concurrent.futures import ThreadPoolExecutor

        n_loaders = int(os.environ.get("HUB_CREATION_LOADERS", "8"))
        to_create = [
            (id, connection_string, timeout)
            for id, connection_string, timeout in active_mountpoints
            if id not in active_streams
        ]
        if to_create:

            def loader(args):
                creation_thread(*args)

            with ThreadPoolExecutor(max_workers=n_loaders) as executor:
                executor.map(loader, to_create)

        time.sleep(10)


def handle_events(name: str, sock):

    setproctitle.setproctitle(name)
    print(f"Thread {name}")

    sender = context.socket(zmq.PUSH)
    sender.bind(f"tcp://*:{ZMQ_PULL_PORT}")
    selector.register(sock, selectors.EVENT_READ)

    while not run_event.is_set():

        events = selector.select(timeout=2.0)

        for key, _ in events:
            conn = key.fileobj
            data = conn.recv(RECV_BUFFER_SIZE)

            if conn == sock:
                # remove a connection
                conn.recv(10)
                while not enable_queue.empty():
                    fd = int(enable_queue.get())
                    enable_queue.task_done()
                    # fd = int(fd_b)
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


def worker(name: str, w_id: int, url: str):

    setproctitle.setproctitle(name)
    print(f"Thread {name}")

    receiver = context.socket(zmq.PULL)
    receiver.connect(f"tcp://localhost:{ZMQ_PULL_PORT}")

    o = urlparse(url)

    # Initialize MQTT Client with robust reconnect
    mqtt_client_id = f"n2m-{w_id:02d}-{generate_random_string(8)}"
    mqtt_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id
    )
    if o.username and o.password:
        mqtt_client.username_pw_set(o.username, o.password)

    mqtt_connected = threading.Event()
    mqtt_should_stop = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"MQTT client {mqtt_client_id} connected.")
            mqtt_connected.set()
        else:
            print(f"MQTT client {mqtt_client_id} failed to connect, rc={rc}")
            mqtt_connected.clear()

    def on_disconnect(client, userdata, rc, properties=None, reason_code=None):
        print(f"MQTT client {mqtt_client_id} disconnected (rc={rc})")
        mqtt_connected.clear()
        if not mqtt_should_stop.is_set():
            # Try to reconnect in background
            while not mqtt_should_stop.is_set():
                try:
                    print(f"MQTT client {mqtt_client_id} attempting reconnect...")
                    client.reconnect()
                    return
                except Exception as e:
                    print(f"MQTT reconnect failed: {e}")
                    time.sleep(2)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect

    # Connect with retry
    for attempt in range(5):
        try:
            mqtt_client.connect(o.hostname, o.port)
            break
        except Exception as e:
            print(f"MQTT initial connect failed (attempt {attempt+1}/5): {e}")
            time.sleep(2)
    mqtt_client.loop_start()  # Start the MQTT client loop

    # Wait for connection
    if not mqtt_connected.wait(timeout=10):
        print(
            f"MQTT client {mqtt_client_id} could not connect after 10s, continuing anyway."
        )

    print(f"Started MQTT client {mqtt_client_id}")

    while not run_event.is_set():
        try:
            fd, data = receiver.recv_pyobj()
            # print(f"Receiving data for fd={fd}, worker {w_id}, bytes={len(data)}")
        except Exception as e:
            print(f"ZMQ receive error: {e}")
            time.sleep(1)
            continue

        if fd in list(connections.keys()):
            try:
                url = connections[fd].url
                o2 = urlparse(url)
                p2 = o2.path[1:]
                topic = f"s2d/osr/{p2}/rtcm"
                connections[fd]._buffer.write(data)
                connections[fd]._buffer.seek(0)

                if PARSE_RAW:
                    keep_reading = True
                    # TODO choose raw format depending on stream
                    while keep_reading:
                        chunk = connections[fd]._buffer.read(1)
                        while (chunk != b"\xd3") and keep_reading:
                            chunk = connections[fd]._buffer.read(1)
                        print("RTCM")
                        length_data = connections[fd]._buffer.read(2)
                        length = (length_data[0] << 8) + length_data[1]
                        if len(connections[fd]._buffer.getvalue()) < length:
                            remaining_buffer = connections[fd]._buffer.read()
                            connections[fd]._buffer = io.BytesIO()
                            connections[fd]._buffer.write(b"\xd3" + length_data)
                            connections[fd]._buffer.seek(0)
                            keep_reading = False
                            continue
                        packet_data = connections[fd]._buffer.read(length)
                        crc24_data = connections[fd]._buffer.read(3)
                        message_number = (packet_data[0] << 8) + packet_data[1]
                        message_number >>= 4
                        topicM = f"{topic}/{message_number}"
                        try:
                            if mqtt_connected.is_set():
                                mqtt_client.publish(topicM, data)
                        except Exception as e:
                            print(f"MQTT publish error: {e}")
                        # check if puffer is empty
                        if connections[fd]._buffer.tell() == len(
                            connections[fd]._buffer.getvalue()
                        ):
                            keep_reading = False
                else:
                    if len(data) > 0:
                        try:
                            if mqtt_connected.is_set():
                                mqtt_client.publish(topic, data)
                        except Exception as e:
                            print(f"MQTT publish error: {e}")

            except Exception as e:
                traceback.print_exc()
                print(e)

        time.sleep(0.000000001)

    mqtt_should_stop.set()
    mqtt_client.loop_stop()  # Stop the MQTT client loop


def main(name: str):

    sock1, sock2 = socket.socketpair()

    # start worker threads
    MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
    MQTT_PORT = os.environ.get("MQTT_PORT", "1883")
    MQTT_USER = os.environ.get("MQTT_USER", "user")
    MQTT_PSWD = os.environ.get("MQTT_PSWD", "pswd")
    mqtt_url = f"mqtt://{MQTT_USER}:{MQTT_PSWD}@{MQTT_HOST}:{MQTT_PORT}"
    print(f"MQTT_URL: {mqtt_url}")
    for i in range(WORKERS):
        t = threading.Thread(
            target=worker,
            args=(
                f"HUB/WRK/{i:02d}",
                i,
                mqtt_url,
            ),
        )
        t.daemon = True
        t.start()
    time.sleep(3)

    # start checker thread
    db_thread = threading.Thread(
        target=check_mountpoints,
        args=(
            "HUB/CHK",
            sock1,
        ),
    )
    db_thread.daemon = True
    db_thread.start()

    # start selector
    ev_thread = threading.Thread(
        target=handle_events,
        args=(
            "HUB/EVE",
            sock2,
        ),
    )
    ev_thread.daemon = True
    ev_thread.start()

    setproctitle.setproctitle(name)
    print(f"Thread {name}")

    while not run_event.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main("HUB/MAIN")
