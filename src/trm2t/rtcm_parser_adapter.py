"""
RTCM Parser with automatic native/pure-Python fallback.

This module attempts to use the fast C++ native parser, but falls back
to the pure Python implementation if the native module is not available.
"""

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

PRE_RTCM = b"\xd3"

# Try to import native C++ parser
try:
    from .rtcm_parser_native import RTCMParser as NativeRTCMParser

    NATIVE_AVAILABLE = True
    logger.info("Using native C++ RTCM parser (high performance)")
except ImportError as e:
    NATIVE_AVAILABLE = False
    logger.warning(f"Native C++ parser not available, using pure Python: {e}")


class RTCMParserAdapter:
    """
    Adapter class that provides a unified interface for both native and Python parsers.

    Automatically uses the native C++ parser if available, otherwise falls back to Python.
    Maintains the same API as the original Python RTCMParser for drop-in compatibility.
    """

    def __init__(self, validate_crc: bool = False):
        """
        Initialize the RTCM parser.

        Args:
            validate_crc: Whether to validate CRC24 of messages (default: False).
        """
        self.validate_crc = validate_crc
        self.last_error = None

        if NATIVE_AVAILABLE:
            self._native_parser = NativeRTCMParser(validate_crc)
            self._use_native = True
        else:
            self._native_parser = None
            self._use_native = False

    def parse(self, buffer: io.BytesIO) -> Optional[Tuple[int, bytes]]:
        """
        Parse next complete RTCM message from buffer.

        Args:
            buffer: The BytesIO buffer containing RTCM data.

        Returns:
            Tuple of (message_id, raw_message) if a complete message is found, None otherwise.
        """
        if self._use_native:
            return self._parse_native(buffer)
        else:
            return self._parse_python(buffer)

    def _parse_native(self, buffer: io.BytesIO) -> Optional[Tuple[int, bytes]]:
        """Parse using native C++ implementation."""
        start_pos = buffer.tell()

        # Get remaining data from current position
        remaining_data = buffer.read()
        if not remaining_data:
            buffer.seek(start_pos)
            return None

        # Call native parser
        result = self._native_parser.parse(remaining_data)

        if result is None:
            # No complete message found
            buffer.seek(start_pos)
            return None

        message_id, raw_message, bytes_consumed = result

        # Update buffer position
        buffer.seek(start_pos + bytes_consumed)

        return (message_id, raw_message)

    def _parse_python(self, buffer: io.BytesIO) -> Optional[Tuple[int, bytes]]:
        """Parse using pure Python implementation (fallback)."""
        start_pos = buffer.tell()

        try:
            # Look for RTCM preamble (0xd3)
            preamble = buffer.read(1)
            if not preamble:
                buffer.seek(start_pos)
                return None

            if preamble != PRE_RTCM:
                # Not at a valid RTCM boundary, search for next preamble
                current_pos = buffer.tell()
                remaining = buffer.read()
                prefix_idx = remaining.find(PRE_RTCM)

                if prefix_idx == -1:
                    buffer.seek(start_pos)
                    return None

                # Found preamble, seek to it
                buffer.seek(current_pos + prefix_idx)
                preamble = buffer.read(1)
                if not preamble:
                    buffer.seek(start_pos)
                    return None

            # Read length field (2 bytes)
            length_bytes = buffer.read(2)
            if len(length_bytes) < 2:
                buffer.seek(start_pos)
                return None

            # Extract message length: 10 bits after 6 reserved bits
            length = ((length_bytes[0] & 0b00000011) << 8) + length_bytes[1]

            # Read message data
            message_data = buffer.read(length)
            if len(message_data) < length:
                buffer.seek(start_pos)
                return None

            # Read CRC (3 bytes)
            crc_bytes = buffer.read(3)
            if len(crc_bytes) < 3:
                buffer.seek(start_pos)
                return None

            # Construct full message
            full_message = PRE_RTCM + length_bytes + message_data + crc_bytes

            # Extract message ID (first 12 bits of message_data)
            if len(message_data) >= 2:
                message_id = ((message_data[0] << 8) | message_data[1]) >> 4
            else:
                message_id = 0

            return (message_id, full_message)

        except Exception as e:
            self.last_error = str(e)
            buffer.seek(start_pos)
            return None

    def parse_all(self, buffer: io.BytesIO) -> list:
        """
        Parse all available complete RTCM messages from buffer.

        Args:
            buffer: The BytesIO buffer containing RTCM data.

        Returns:
            List of (message_id, raw_message) tuples.
        """
        messages = []
        buffer.seek(0)

        while True:
            result = self.parse(buffer)
            if result is None:
                break
            messages.append(result)

        return messages


# Export as RTCMParser for drop-in compatibility
RTCMParser = RTCMParserAdapter
