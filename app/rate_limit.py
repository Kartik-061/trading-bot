"""
app/rate_limit.py
Shared Limiter instance. Lives in its own module so both main.py (which
registers the middleware) and routes.py (which applies @limiter.limit(...)
to specific expensive endpoints) can import it without a circular import.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
