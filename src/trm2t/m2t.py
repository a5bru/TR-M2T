"""This script subscribes to an MQTT broker and outputs received messages to stdout or to a tcp server."""

import sys
import os
import socket
import time
import selectors
from dotenv import load_dotenv
import argparse
import paho.mqtt.client as mqtt
import threading

# Configuration


BUFFER_SIZE = 1024 * 2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if os.path.exists(ENV_PATH):
    print("Loading environment from:", ENV_PATH)

load_dotenv(ENV_PATH, verbose=False)

# MQTT broker settings
# Change to your broker's address
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
# Change if your broker uses a different port
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
# Change to your desired topic path
MQTT_PATH = os.environ.get("MQTT_PATH", "s2d/osr")

# MQTT authentication settings
# Change to your MQTT username
MQTT_USER = os.environ.get("MQTT_USER", "")
# Change to your MQTT password
MQTT_PSWD = os.environ.get("MQTT_PSWD", "")

parser = argparse.ArgumentParser()

event_handler = threading.Event()
client_lock = threading.Lock()

connected_clients = set()
selector = selectors.DefaultSelector()
s_mqtt, s_tcp = socket.socketpair()

# Settings for MQTT
parser.add_argument("-a", default=MQTT_HOST, type=str, help="Set the MQTT host")
parser.add_argument("-p", default=MQTT_PORT, type=int, help="Set the MQTT port")
parser.add_argument(
    "-m", default=MQTT_PATH, type=str, help="Set the root topic for the data"
)
parser.add_argument("-n", default=MQTT_USER, type=str, help="Set the MQTT username")
parser.add_argument("-c", default=MQTT_PSWD, type=str, help="Set the MQTT password")
# Settings for output
parser.add_argument(
    "-P",
    type=int,
    default=-1,
    help="Set the TCP port for output (if not set, output to stdout)",
)
parser.add_argument("-v", action="store_true", help="Enable verbose output")
args = parser.parse_args()


# --- TCP callbacks ---


def tcp_server_thread(
    port: int, socket_data: socket.socket = s_tcp, bind_address: str = ""
):

    selector.register(socket_data, selectors.EVENT_READ, data="socketpair")

    if port > 0:
        print(f"Starting TCP server on port {port}")
        # Setup TCP server
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((bind_address, port))
        server_socket.listen()
        server_socket.setblocking(False)
        selector.register(server_socket, selectors.EVENT_READ, data="server")

    else:
        print("Outputting data to stdout")

    def accept_connection(sock):
        client_socket, addr = sock.accept()
        print(f"Accepted connection from {addr}")
        client_socket.setblocking(False)
        with client_lock:
            connected_clients.add(client_socket)
        # no registering client sockets, we use socketpair for notification
        # selector.register(client_socket, selectors.EVENT_READ, data="client")

    def handle_client(sock):
        try:
            data = sock.recv(BUFFER_SIZE)
            if data:
                sock.sendall(data)
            else:
                raise ConnectionResetError()
        except (ConnectionResetError, BrokenPipeError):
            print("Client disconnected", sock.getpeername())
            selector.unregister(sock)
            with client_lock:
                connected_clients.remove(sock)
            sock.close()

    def handle_pair(sock):
        clients_to_remove = []
        try:
            data = sock.recv(BUFFER_SIZE)
            if data:
                if port > 0:
                    with client_lock:
                        for client in connected_clients.copy():
                            try:
                                client.sendall(data)
                            except (BrokenPipeError, ConnectionResetError) as ce:
                                print("Client disconnected")
                                clients_to_remove.append(client)
                else:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
            else:
                pass  # No data received (0 bytes means graceful close)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"Socket pair error: {e}")
            # Don't close the socket pair itself, just log the error
            # The socketpair might recover on next MQTT message
        except Exception as e:
            print(f"Unexpected error on socket pair: {e}")

        for client in clients_to_remove:
            try:
                selector.unregister(client)
            except KeyError:
                pass  # Already unregistered
            with client_lock:
                connected_clients.discard(client)
            client.close()

    while not event_handler.is_set():
        # wait for events, max 0.1 seconds
        events = selector.select(timeout=0.1)
        for key, _ in events:
            conn = key.fileobj

            if conn == s_tcp:
                if args.v:
                    print("Data available on socket pair")
                handle_pair(key.fileobj)

            if port <= 0:
                continue

            if conn == server_socket:
                if args.v:
                    print("New connection on server socket")
                accept_connection(key.fileobj)

            elif conn in connected_clients.copy():
                if args.v:
                    print("Data available on client socket")
                handle_client(key.fileobj)


# --- MQTT callbacks ---


def broadcast_data(data, socket_out=s_mqtt):
    socket_out.sendall(data)


# Callback for when the client connects to the broker
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT broker successfully!")
        print(f"Subscribing to topic: {args.m}")
        client.subscribe(args.m)
    else:
        print(f"Failed to connect, return code {reason_code}")


# Callback for when a message is received
def on_message(client, userdata, msg):
    if args.v:
        print(
            f"Received message on topic {msg.topic} with payload size {len(msg.payload)} bytes"
        )
    broadcast_data(msg.payload, socket_out=s_mqtt)


def mqtt_sub_thread():
    # Create an MQTT client instance
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    # Set username and password
    if args.n and args.c:
        client.username_pw_set(args.n, args.c)

    # Attach callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to the MQTT broker
    client.connect(args.a, args.p, 60)

    # Start the MQTT client loop
    client.loop_forever()
    while not event_handler.is_set():
        time.sleep(0.1)
    client.loop_stop()


if __name__ == "__main__":

    tcp_thread = threading.Thread(target=tcp_server_thread, args=(args.P, s_tcp))
    tcp_thread.daemon = True
    tcp_thread.start()

    mqtt_thread = threading.Thread(target=mqtt_sub_thread)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    try:
        while not event_handler.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)
