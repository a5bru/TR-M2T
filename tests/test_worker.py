"""Tests for worker module."""

import pytest
from trm2t.worker import generate_random_string


def test_generate_random_string_length():
    """Test that generated random string has correct length."""
    for length in [5, 8, 10, 16, 32]:
        result = generate_random_string(length)
        assert len(result) == length


def test_generate_random_string_characters():
    """Test that generated string contains only alphanumeric characters."""
    result = generate_random_string(100)
    assert result.isalnum()


def test_generate_random_string_uniqueness():
    """Test that generated strings are unique (statistically)."""
    strings = [generate_random_string(10) for _ in range(100)]
    # All strings should be unique (with very high probability)
    assert len(set(strings)) == 100


def test_generate_random_string_zero_length():
    """Test edge case with zero length."""
    result = generate_random_string(0)
    assert result == ""


def test_generate_random_string_single_char():
    """Test edge case with single character."""
    result = generate_random_string(1)
    assert len(result) == 1
    assert result.isalnum()
