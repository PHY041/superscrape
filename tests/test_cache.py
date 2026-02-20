"""Tests for cache module."""

from unittest.mock import patch

from superscrape.core.cache import cache_key, get_cached, save_cache


def test_cache_key_deterministic():
    k1 = cache_key("wireless earbuds", 10)
    k2 = cache_key("wireless earbuds", 10)
    assert k1 == k2


def test_cache_key_varies_by_keyword():
    k1 = cache_key("wireless earbuds", 10)
    k2 = cache_key("portable blender", 10)
    assert k1 != k2


def test_cache_key_varies_by_top_n():
    k1 = cache_key("wireless earbuds", 10)
    k2 = cache_key("wireless earbuds", 20)
    assert k1 != k2


def test_cache_key_varies_by_platform():
    k1 = cache_key("test", 10, "amazon")
    k2 = cache_key("test", 10, "walmart")
    assert k1 != k2


def test_save_and_get_cached(tmp_path):
    with patch("superscrape.core.cache.CACHE_DIR", tmp_path):
        data = {"products": [{"title": "Test"}]}
        save_cache("blender", 5, data)
        result = get_cached("blender", 5)
        assert result is not None
        assert result["products"][0]["title"] == "Test"


def test_cache_miss(tmp_path):
    with patch("superscrape.core.cache.CACHE_DIR", tmp_path):
        result = get_cached("nonexistent", 10)
        assert result is None


def test_cache_expired(tmp_path):
    with patch("superscrape.core.cache.CACHE_DIR", tmp_path):
        data = {"products": []}
        save_cache("test", 5, data)

        # Should return data with long TTL
        result = get_cached("test", 5, ttl=86400)
        assert result is not None

        # Should return None with 0 TTL (immediately expired)
        result = get_cached("test", 5, ttl=0)
        assert result is None
