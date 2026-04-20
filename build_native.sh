#!/bin/bash
# Build and install script for TR-M2T with native C++ extensions

set -e

echo "=== Building TR-M2T with Native C++ Extensions ==="

# Check for required tools
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

if ! command -v g++ &> /dev/null; then
    echo "Error: g++ not found. Please install build-essential:"
    echo "  sudo apt-get install build-essential"
    exit 1
fi

# Detect if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: Not in a virtual environment"
    echo "Installing with --user flag or use --break-system-packages if needed"
    PIP_FLAGS="--user"
else
    echo "Virtual environment detected: $VIRTUAL_ENV"
    PIP_FLAGS=""
fi

echo "Installing pybind11..."
pip install $PIP_FLAGS pybind11>=2.10.0

echo ""
echo "Building C++ extension..."
python3 setup.py build_ext --inplace

echo ""
echo "Installing package..."
pip install $PIP_FLAGS -e .

echo ""
echo "=== Build Complete ==="
echo ""
echo "Testing if native parser is available..."
python3 -c "from trm2t.rtcm_parser_adapter import NATIVE_AVAILABLE; print('Native parser:', 'Available ✓' if NATIVE_AVAILABLE else 'Not Available (using Python fallback)')"

echo ""
echo "Done! Restart your services to use the new native parser."
