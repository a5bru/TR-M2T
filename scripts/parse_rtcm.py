#!/usr/bin/env python3
"""
Simple RTCM parser that reads from stdin and outputs message information.

Usage:
    cat rtcm_data.bin | python parse_rtcm.py
    python parse_rtcm.py < rtcm_data.bin
"""

import sys
import io
import argparse
import time

# Try to use pyrtcm if available, otherwise use the local RTCMParser
try:
    from pyrtcm import RTCMReader

    USE_PYRTCM = True
except ImportError:
    pass
finally:
    USE_PYRTCM = False
    # Fallback to local implementation
    sys.path.insert(0, "../src")
    from trm2t.connection import RTCMParser


def parse_with_pyrtcm():
    """Parse RTCM data using pyrtcm library."""
    reader = RTCMReader(sys.stdin.buffer, bufsize=1024)
    msg_count = 0

    try:

        for raw_data, parsed_msg in reader:
            msg_count += 1
            if hasattr(parsed_msg, "identity"):
                print(
                    f"{time.time():.3f} Message {msg_count:5d}: {parsed_msg.identity} ({len(raw_data)} bytes)"
                )
            else:
                print(f"Message {msg_count}: Unknown type ({len(raw_data)} bytes)")

            if args.verbose:
                print(f"  Raw: {raw_data.hex()[:80]}...")
                print(f"  Parsed: {parsed_msg}")
                print()
    except KeyboardInterrupt:
        pass

    print(f"\nTotal messages parsed: {msg_count}")


def parse_with_local():
    """Parse RTCM data using local RTCMParser."""
    parser = RTCMParser(validate_crc=args.validate_crc)
    buffer = io.BytesIO()
    msg_count = 0

    try:
        # Read stdin in chunks
        while True:
            ts = time.time()
            print("")
            print(f"{ts:.3f}...looping")
            chunk = sys.stdin.buffer.read(1024)
            if not chunk:
                break

            # Append to buffer
            buffer.seek(0, io.SEEK_END)
            buffer.write(chunk)
            buffer.seek(0)

            # Parse all available messages
            while True:
                tsi = time.time()
                print(f"{tsi:.3f}...parsing")
                result = parser.parse(buffer)
                if result is None:
                    # No complete message, keep remaining data
                    remaining = buffer.read()
                    buffer = io.BytesIO(remaining)
                    break

                message_id, raw_message = result
                msg_count += 1

                if tsi - ts > 2.0:
                    print(f"{tsi:.3f} Message {msg_count:5d}: Too late for {tsi-ts:.3f} seconds")
                    break

                print(
                    f"{tsi:.3f} Message {msg_count:5d}: Type {message_id} ({len(raw_message)} bytes)"
                )

                if args.verbose:
                    print(f"  Raw: {raw_message.hex()[:80]}...")
                    print()

    except KeyboardInterrupt:
        pass

    if parser.last_error:
        print(f"\nLast error: {parser.last_error}", file=sys.stderr)

    print(f"\nTotal messages parsed: {msg_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse RTCM messages from stdin")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed message information"
    )
    parser.add_argument(
        "--validate-crc", action="store_true", help="Validate CRC24 checksums (local parser only)"
    )
    parser.add_argument(
        "--use-local",
        action="store_true",
        help="Force use of local RTCMParser even if pyrtcm is available",
    )

    args = parser.parse_args()

    if USE_PYRTCM and not args.use_local:
        print("Using pyrtcm library", file=sys.stderr)
        parse_with_pyrtcm()
    else:
        print("Using local RTCMParser", file=sys.stderr)
        parse_with_local()
