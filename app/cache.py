"""
app/cache.py
Simple in-memory TTL cache. Not Redis - doesn't need to be, for a
single-instance deployment like this. Cuts down repeated Yahoo Finance
calls when multiple people (or the same person refreshing) hit the same
screener page within a short window - real cost saving given how slow
and rate-limit-prone yfinance already is.
"""
import time
from functools import wraps

_cache_store = {}


def _make_hashable(val):
    """Lists/dicts aren't hashable and can't be used as dict keys directly -
    convert them to a hashable equivalent so caching a function that takes
    a list argument (e.g. a symbols list) doesn't crash."""
    if isinstance(val, list):
        return tuple(_make_hashable(v) for v in val)
    if isinstance(val, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in val.items()))
    return val


def ttl_cache(ttl_seconds: int = 300):
    """Decorator - caches a function's return value per unique set of
    arguments for ttl_seconds. Not thread-safe for writes, but that's fine
    here: worst case is one redundant fetch, not corrupted data."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            hashable_args = tuple(_make_hashable(a) for a in args)
            hashable_kwargs = tuple(sorted((k, _make_hashable(v)) for k, v in kwargs.items()))
            key = (func.__name__, hashable_args, hashable_kwargs)
            now = time.time()

            if key in _cache_store:
                value, expires_at = _cache_store[key]
                if now < expires_at:
                    return value

            result = func(*args, **kwargs)
            _cache_store[key] = (result, now + ttl_seconds)
            return result
        return wrapper
    return decorator


def clear_cache():
    """Useful for tests, or a future admin endpoint to force-refresh."""
    _cache_store.clear()
