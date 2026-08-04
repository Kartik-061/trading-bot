"""
app/auth.py
Simple shared-secret API key check - not a full user/login system, since
this bot only ever has one real user (you). If API_KEY is left empty in
.env, auth is skipped entirely (convenient for local dev). Once deployed
somewhere public, set a real random API_KEY and every request must include
it in the X-API-Key header.
"""
import secrets
from fastapi import Header, HTTPException

from app.config import settings


async def verify_api_key(x_api_key: str = Header(default=None)):
    """FastAPI dependency - add to any route (or the whole router) to
    require the correct key. Uses constant-time comparison so response
    timing can't be used to guess the key character by character."""
    if not settings.API_KEY:
        return  # no key configured - auth disabled, local dev convenience

    if not x_api_key or not secrets.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
