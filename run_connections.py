import sys
import sqlite3
import zmq
import socket
import select
import selectors
import time
import threading
import base64
import queue
import threading
import string
import os
import random
import pickle

import paho.mqtt.client as mqtt

from urllib.parse import urlparse

context = zmq.Context()
selector = selectors.DefaultSelector()
connections = {}
#data_queue = queue.Queue()

WORKERS = int(os.environ.get("MQTT_HUB_WORKERS", "2"))

ZMQ_PULL_PORT = int(os.environ.get("ZMQ_PULL_PORT", "6969"))


def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string


def create_tcp_client(url):

    # Parse url info
    o = urlparse(url)
    host = o.hostname
    port = o.port
    path = o.path
    auth = base64.b64encode(f"{o.username}:{o.password}".encode()).decode()

    # Create a TCP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (host, port)  # Replace with your server's IP and port

    try:
        client_socket.connect(server_address)

    except BlockingIOError:
        # This is expected for non-blocking sockets
        pass

    except Exception as e:
        print(e)
        return -1

    try:
        request = f"GET {path} HTTP/1.0\r\n"
        request += "User-Agent: Ntrip N2Mqtt/v0.1\r\n"
        request += "Connection: close\r\n"
        request += f"Host: {host}\r\n"
        request += f"Authorization: Basic {auth}\r\n"
        request += "\r\n"
        client_socket.sendall(request.encode()) 
        seconds = 2.0 
        readable, _, _ = select.select([client_socket, ], [], [], seconds)
        if not readable:
            assert False, f"E: {path}: No Response within {seconds} secs."
        data = client_socket.recv(1024)
        assert b"200" in data, f"E: {path}: No Response 200"
        assert b"SOURCETABLE" not in data, f"E: {path}: No Data availale"
    except AssertionError as e:
        print(e, file=sys.stderr)
        return -1

    client_socket.setblocking(0)  # Set socket to non-blocking
    return client_socket


def fetch_active_mountpoints():
    conn = sqlite3.connect('mountpoints.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, connection_string FROM mountpoints WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    return rows


def check_mountpoints():
    while True:
        print("Check for active mountpoints")
        active_mountpoints = fetch_active_mountpoints()
        active_ids = set(mp[0] for mp in active_mountpoints)

        for conn in list(connections.keys()):
            id = connections[conn]["id"]
            if id not in active_ids:
                o = urlparse(connections[conn]["url"])
                print(f"I: {o.path}: Closing connection")
                selector.unregister(conn)
                conn.close()
                del connections[conn]

        for id, connection_string in active_mountpoints:
            if id not in connections:
                o = urlparse(connection_string)
                print(f"I: {o.path}: Opening connection")
                conn = create_tcp_client(connection_string)
                if conn != -1:
                    selector.register(conn, selectors.EVENT_READ)
                    connections[conn] = {"id": id, "url": connection_string}

        time.sleep(10)


def handle_events():

    sender = context.socket(zmq.PUSH)
    sender.bind(f"tcp://*:{ZMQ_PULL_PORT}")

    while True:
        events = selector.select(timeout=None)
        for key, mask in events:
            conn = key.fileobj
            data = conn.recv(1024)
            if data:
                sender.send_pyobj((connections[conn]["id"], data))
                #data_queue.put((connections[conn]["id"], data))
            else:
                selector.unregister(conn)
                conn.close()
                del connections[conn]

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
        #item = data_queue.get()
        #if item is None:
        #    break
        #conn_sock, data = item
        #data_queue.task_done()
        conn_id, data = receiver.recv_pyobj()

        for conn_sock in list(connections.keys()):
            if conn_id == connections[conn_sock]["id"]:
                o2 = urlparse(connections[conn_sock]["url"])
                p2 = o2.path[1:]
                topic = f"s2d/osr/{p2}/rtcm"
                #assert len(data) > 0, f"E: {topic}: Empty response"
                if len(data) > 0:
                    # Publish received data to MQTT
                    mqtt_client.publish(topic, data)
                break;
        time.sleep(0.000000001)

    mqtt_client.loop_stop()  # Stop the MQTT client loop


def main():

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
    db_thread = threading.Thread(target=check_mountpoints)
    db_thread.daemon = True
    db_thread.start()

    # start selector
    handle_events()


if __name__ == "__main__":
    main()

