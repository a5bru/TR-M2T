"""Pytest configuration and shared fixtures."""
import pytest
import sys
import os

# Add src directory to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

@pytest.fixture
def sample_fixture():
    return "Hello, World!"