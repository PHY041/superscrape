"""Tests for retry_with_backoff utility."""

from unittest.mock import patch

import pytest

from superscrape.core.retry import retry_with_backoff


def test_retry_success_first_try():
    result = retry_with_backoff(lambda: 42, max_retries=3)
    assert result == 42


def test_retry_success_after_failures():
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient error")
        return "ok"

    with patch("superscrape.core.retry.time.sleep"):
        result = retry_with_backoff(flaky, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 3


def test_retry_exhausted():
    def always_fail():
        raise RuntimeError("permanent error")

    with patch("superscrape.core.retry.time.sleep"):
        with pytest.raises(RuntimeError, match="permanent error"):
            retry_with_backoff(always_fail, max_retries=3, base_delay=0.01)


def test_retry_respects_max_retries():
    call_count = 0

    def counting_fail():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")

    with patch("superscrape.core.retry.time.sleep"):
        with pytest.raises(ValueError):
            retry_with_backoff(counting_fail, max_retries=5, base_delay=0.01)
        assert call_count == 5
