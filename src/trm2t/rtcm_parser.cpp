/*
 * Fast RTCM3 Parser - C++ implementation with pybind11 bindings
 * 
 * This module provides a high-performance RTCM message parser that:
 * - Releases the GIL during parsing for true parallelism
 * - Uses efficient memory operations
 * - Can process multiple messages from a streaming buffer
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdint>
#include <cstring>
#include <vector>
#include <tuple>
#include <optional>
#include <algorithm>

namespace py = pybind11;

constexpr uint8_t RTCM_PREAMBLE = 0xD3;

class RTCMParser {
private:
    bool validate_crc;
    std::string last_error;

    // Fast CRC24Q calculation for RTCM
    uint32_t calculate_crc24(const uint8_t* data, size_t length) const {
        uint32_t crc = 0;
        
        for (size_t i = 0; i < length; i++) {
            crc ^= static_cast<uint32_t>(data[i]) << 16;
            
            for (int j = 0; j < 8; j++) {
                crc <<= 1;
                if (crc & 0x1000000) {
                    crc ^= 0x1864CFB;
                }
            }
        }
        
        return crc & 0xFFFFFF;
    }

public:
    RTCMParser(bool validate_crc = false) : validate_crc(validate_crc) {}

    std::string get_last_error() const {
        return last_error;
    }

    // Parse a single RTCM message from bytes buffer
    // Returns: tuple of (message_id, raw_message_bytes, bytes_consumed)
    //          or empty optional if incomplete message
    std::optional<std::tuple<uint16_t, py::bytes, size_t>> parse(const py::bytes& buffer_py) {
        // Release GIL for CPU-bound parsing
        py::gil_scoped_release release;
        
        const char* buffer_ptr = PyBytes_AsString(buffer_py.ptr());
        if (!buffer_ptr) {
            py::gil_scoped_acquire acquire;
            last_error = "Invalid buffer";
            return std::nullopt;
        }
        
        size_t buffer_size = PyBytes_Size(buffer_py.ptr());
        const uint8_t* data = reinterpret_cast<const uint8_t*>(buffer_ptr);
        
        // Find preamble
        const uint8_t* preamble_pos = static_cast<const uint8_t*>(
            memchr(data, RTCM_PREAMBLE, buffer_size)
        );
        
        if (!preamble_pos) {
            // No preamble found
            return std::nullopt;
        }
        
        size_t offset = preamble_pos - data;
        size_t remaining = buffer_size - offset;
        
        // Need at least: preamble(1) + length(2) + crc(3) = 6 bytes minimum
        if (remaining < 6) {
            return std::nullopt;
        }
        
        // Read length field (10 bits after 6 reserved bits)
        uint16_t length = ((preamble_pos[1] & 0x03) << 8) | preamble_pos[2];
        
        // Total message size
        size_t message_size = 3 + length + 3;  // preamble(1) + length(2) + data + crc(3)
        
        if (remaining < message_size) {
            // Not enough data for complete message
            return std::nullopt;
        }
        
        // Validate CRC if enabled
        if (validate_crc) {
            uint32_t calculated_crc = calculate_crc24(preamble_pos, 3 + length);
            uint32_t message_crc = (preamble_pos[3 + length] << 16) |
                                   (preamble_pos[3 + length + 1] << 8) |
                                   preamble_pos[3 + length + 2];
            
            if (calculated_crc != message_crc) {
                // CRC mismatch - skip this message
                // Try to find next preamble after current position
                if (remaining > message_size) {
                    const uint8_t* next_preamble = static_cast<const uint8_t*>(
                        memchr(preamble_pos + 1, RTCM_PREAMBLE, remaining - 1)
                    );
                    if (next_preamble) {
                        // Recursively try next message (note: may hit stack limits on bad data)
                        // In practice, consider returning error instead
                        py::gil_scoped_acquire acquire;
                        last_error = "CRC mismatch";
                    }
                }
                return std::nullopt;
            }
        }
        
        // Extract message ID (first 12 bits of message data)
        uint16_t message_id = 0;
        if (length >= 2) {
            message_id = ((preamble_pos[3] << 4) | (preamble_pos[4] >> 4));
        }
        
        // Re-acquire GIL to create Python bytes object
        py::gil_scoped_acquire acquire;
        py::bytes message_bytes(reinterpret_cast<const char*>(preamble_pos), message_size);
        
        return std::make_tuple(message_id, message_bytes, offset + message_size);
    }

    // Parse all complete messages from buffer
    // Returns: list of (message_id, raw_message_bytes) tuples
    std::vector<std::tuple<uint16_t, py::bytes>> parse_all(const py::bytes& buffer_py) {
        std::vector<std::tuple<uint16_t, py::bytes>> messages;
        
        const char* buffer_ptr = PyBytes_AsString(buffer_py.ptr());
        if (!buffer_ptr) {
            return messages;
        }
        
        size_t buffer_size = PyBytes_Size(buffer_py.ptr());
        size_t offset = 0;
        
        while (offset < buffer_size) {
            // Create view of remaining buffer
            py::bytes remaining_buffer(buffer_ptr + offset, buffer_size - offset);
            
            auto result = parse(remaining_buffer);
            if (!result) {
                break;
            }
            
            auto [msg_id, msg_bytes, consumed] = *result;
            messages.emplace_back(msg_id, msg_bytes);
            offset += consumed;
        }
        
        return messages;
    }

    // Stream-based parsing with position tracking
    // This variant is optimized for BytesIO-like usage
    std::optional<std::tuple<uint16_t, py::bytes>> parse_from_position(
        const py::bytes& buffer_py, size_t position
    ) {
        const char* buffer_ptr = PyBytes_AsString(buffer_py.ptr());
        if (!buffer_ptr) {
            return std::nullopt;
        }
        
        size_t buffer_size = PyBytes_Size(buffer_py.ptr());
        
        if (position >= buffer_size) {
            return std::nullopt;
        }
        
        // Create view from position
        py::bytes view(buffer_ptr + position, buffer_size - position);
        auto result = parse(view);
        
        if (!result) {
            return std::nullopt;
        }
        
        auto [msg_id, msg_bytes, consumed] = *result;
        return std::make_tuple(msg_id, msg_bytes);
    }
};

PYBIND11_MODULE(rtcm_parser_native, m) {
    m.doc() = "Fast RTCM3 message parser with native C++ implementation";

    py::class_<RTCMParser>(m, "RTCMParser")
        .def(py::init<bool>(), py::arg("validate_crc") = false,
             "Initialize RTCM parser\n\n"
             "Args:\n"
             "    validate_crc: Whether to validate CRC24 of messages (default: False)")
        .def("parse", &RTCMParser::parse,
             py::arg("buffer"),
             "Parse a single RTCM message from buffer\n\n"
             "Args:\n"
             "    buffer: bytes object containing RTCM data\n\n"
             "Returns:\n"
             "    Tuple of (message_id, raw_message, bytes_consumed) or None")
        .def("parse_all", &RTCMParser::parse_all,
             py::arg("buffer"),
             "Parse all complete RTCM messages from buffer\n\n"
             "Args:\n"
             "    buffer: bytes object containing RTCM data\n\n"
             "Returns:\n"
             "    List of (message_id, raw_message) tuples")
        .def("parse_from_position", &RTCMParser::parse_from_position,
             py::arg("buffer"), py::arg("position"),
             "Parse message from specific position in buffer\n\n"
             "Args:\n"
             "    buffer: bytes object containing RTCM data\n"
             "    position: byte offset to start parsing from\n\n"
             "Returns:\n"
             "    Tuple of (message_id, raw_message) or None")
        .def_property_readonly("last_error", &RTCMParser::get_last_error,
             "Get last error message");
}
