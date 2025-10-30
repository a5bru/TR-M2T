#!/usr/bin/python3

# copied from https://github.com/aortner/RpiNtripBase/blob/master/rtcmadd1008.py

import sys
import datetime

while True:
    data = sys.stdin.buffer.read(1)
    while (data != b'\xd3'):
        data = sys.stdin.buffer.read(1)

    length_data = sys.stdin.buffer.read(2)
    length = (length_data[0] << 8) + length_data[1]
    packet_data = sys.stdin.buffer.read(length)
    crc24_data = sys.stdin.buffer.read(3)

    message_number = (packet_data[0] << 8) + packet_data[1]
    message_number >>= 4

    dt = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


    sys.stdout.buffer.write(f"{dt}: {message_number}".encode())
    sys.stdout.buffer.write(b"\r\n")
    sys.stdout.flush()

    #sys.stdout.buffer.write(b'\xd3')
    #sys.stdout.buffer.write(length_data)
    #sys.stdout.buffer.write(packet_data)
    #sys.stdout.buffer.write(crc24_data)
    #sys.stdout.flush()
