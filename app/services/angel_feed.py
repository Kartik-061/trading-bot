"""
app/services/angel_feed.py

Real live price feed via Angel One SmartAPI, as a swap-in replacement for
price_feed.py's yfinance-based feed. Data-only: this module never places,
modifies, or cancels an order, so it does NOT need a static outbound IP -
Angel One's own docs are explicit that the static-IP requirement only
applies to order/GTT endpoints, not market-data endpoints like ltpData().
That's what makes this usable on Render's free tier.

Angel One SmartAPI needs a numeric "symboltoken" per instrument, not a
plain ticker string - so the first thing this module does is download and
cache Angel's instrument master (a ~5-10MB JSON of every tradable
instrument) and build a symbol -> (tradingsymbol, token) lookup for NSE
equities. That file changes rarely, so it's cached to disk and only
re-downloaded once a day.

NOTE: this has not been live-tested against Angel One's actual servers -
this sandbox has no network access to angelone.in domains. Test this for
real (a plain script that logs in and fetches one LTP) before flipping
PRICE_FEED=angel on the deployed bot.
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta

import requests

from app.config import settings

logger = logging.getLogger("angel_feed")

_INSTRUMENT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
_INSTRUMENT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".angel_instrument_cache.json")
_INSTRUMENT_CACHE_MAX_AGE = timedelta(hours=24)

_CACHE_TTL_SECONDS = 60  # match price_feed.py - don't hammer the API on every dashboard refresh
_price_cache = {}

_symbol_token_map = None  # bare symbol ("RELIANCE") -> (tradingsymbol "RELIANCE-EQ", token "2885")
_map_lock = threading.Lock()

_smart_api = None
_session_lock = threading.Lock()


def _download_instrument_master() -> list:
    resp = requests.get(_INSTRUMENT_MASTER_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _load_instrument_master() -> list:
    """Disk-cached for 24h so we're not re-downloading a multi-MB file on
    every process restart (Render free tier restarts often)."""
    try:
        if os.path.exists(_INSTRUMENT_CACHE_PATH):
            age = datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(_INSTRUMENT_CACHE_PATH))
            if age < _INSTRUMENT_CACHE_MAX_AGE:
                with open(_INSTRUMENT_CACHE_PATH, "r") as f:
                    return json.load(f)
    except Exception as e:
        logger.warning(f"Angel instrument cache read failed, re-downloading: {e}")

    data = _download_instrument_master()
    try:
        with open(_INSTRUMENT_CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Could not write Angel instrument cache (non-fatal): {e}")
    return data


def _build_symbol_token_map() -> dict:
    instruments = _load_instrument_master()
    mapping = {}
    for row in instruments:
        # NSE equity rows look like {"token": "2885", "symbol": "RELIANCE-EQ",
        # "name": "RELIANCE", "exch_seg": "NSE", "instrumenttype": "", ...}
        if row.get("exch_seg") != "NSE":
            continue
        tradingsymbol = row.get("symbol", "")
        if not tradingsymbol.endswith("-EQ"):
            continue
        bare = tradingsymbol[:-3]  # strip "-EQ"
        mapping[bare] = (tradingsymbol, row.get("token"))
    if not mapping:
        raise RuntimeError("Angel instrument master parsed but produced an empty NSE equity map - check the response format.")
    logger.info(f"Angel instrument map built: {len(mapping)} NSE equities.")
    return mapping


def _get_token(symbol: str) -> tuple:
    global _symbol_token_map
    with _map_lock:
        if _symbol_token_map is None:
            _symbol_token_map = _build_symbol_token_map()
    bare = symbol[:-3] if symbol.endswith(".NS") else symbol
    entry = _symbol_token_map.get(bare)
    if entry is None:
        raise KeyError(f"No Angel One symboltoken found for '{symbol}' - check spelling/whether it's actually an NSE equity.")
    return entry


def _get_session():
    """Logs in once per process, reused across calls. Angel One sessions
    expire (forced logout at midnight per their docs) - if a call fails
    with an auth-looking error, the caller should call _reset_session()
    and retry once."""
    global _smart_api
    with _session_lock:
        if _smart_api is not None:
            return _smart_api
        from SmartApi import SmartConnect
        import pyotp

        if not (settings.ANGEL_API_KEY and settings.ANGEL_CLIENT_ID
                and settings.ANGEL_PASSWORD and settings.ANGEL_TOTP_SECRET):
            raise RuntimeError(
                "PRICE_FEED=angel but ANGEL_API_KEY/ANGEL_CLIENT_ID/ANGEL_PASSWORD/"
                "ANGEL_TOTP_SECRET are not all set."
            )

        api = SmartConnect(api_key=settings.ANGEL_API_KEY)
        totp_secret = settings.ANGEL_TOTP_SECRET.strip().replace(" ", "").upper()
        try:
            totp = pyotp.TOTP(totp_secret).now()
        except Exception as e:
            raise RuntimeError(
                f"ANGEL_TOTP_SECRET doesn't look like a valid base32 TOTP secret "
                f"(got a {len(totp_secret)}-char value). Re-copy it from the SmartAPI "
                f"portal's 2FA/TOTP setup screen - it should be a short (usually "
                f"16-32 char) string of only A-Z and 2-7, no spaces or '='. "
                f"Original error: {e}"
            )
        session = api.generateSession(settings.ANGEL_CLIENT_ID, settings.ANGEL_PASSWORD, totp)
        if not session.get("status"):
            raise RuntimeError(f"Angel One login failed: {session}")
        logger.info("Angel One data session established.")
        _smart_api = api
        return _smart_api


def _reset_session():
    global _smart_api
    with _session_lock:
        _smart_api = None


_AUTH_ERROR_CODES = {"AG8001", "AG8002"}  # Invalid Token / Token expired, per Angel's error codes


def _is_success(resp: dict) -> bool:
    # Real responses seen in production use different key shapes for
    # success: {'status': True, 'errorcode': '', ...} (genuine success,
    # Aug 25) vs {'success': False, 'errorCode': 'AG8001', ...} (auth
    # failure, Aug 24) - different key name AND different casing on the
    # error-code field between the two. Check both rather than betting on
    # one shape and silently misreporting the other as a failure.
    return resp.get("status") is True or resp.get("success") is True


def _is_auth_error(resp: dict) -> bool:
    code = resp.get("errorCode") or resp.get("errorcode") or ""
    if code in _AUTH_ERROR_CODES:
        return True
    msg = str(resp.get("message", "")).lower()
    return "token" in msg or "session" in msg


def _fetch_ltp(symbol: str) -> dict:
    tradingsymbol, token = _get_token(symbol)
    api = _get_session()
    try:
        resp = api.ltpData("NSE", tradingsymbol, token)
        retried = False
    except Exception:
        resp = None
        retried = False

    if resp is None or (not _is_success(resp) and _is_auth_error(resp) and not retried):
        logger.warning(f"Angel session looks invalid/expired for {symbol} ({resp}), re-logging in and retrying once.")
        _reset_session()
        api = _get_session()
        resp = api.ltpData("NSE", tradingsymbol, token)
        retried = True

    if not _is_success(resp):
        raise RuntimeError(f"Angel ltpData failed for {symbol}: {resp}")

    d = resp["data"]
    last_price = float(d["ltp"])
    prev_close = float(d.get("close", last_price))  # 'close' here is prior session close per Angel's docs
    return {
        "symbol": symbol,
        "last_price": round(last_price, 2),
        "previous_close": round(prev_close, 2),
        "day_high": round(float(d.get("high", last_price)), 2),
        "day_low": round(float(d.get("low", last_price)), 2),
        "change_pct": round((last_price - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
        "fetched_at": datetime.utcnow().isoformat(),
    }


def get_angel_ltp(symbol: str) -> dict:
    """Same return shape as price_feed.get_live_price(), same 60s cache
    behavior, so it's a drop-in swap wherever get_live_price() is called."""
    now = datetime.utcnow()
    cached = _price_cache.get(symbol)
    if cached and (now - cached["fetched_at"]).total_seconds() < _CACHE_TTL_SECONDS:
        return cached["data"]

    data = _fetch_ltp(symbol)
    _price_cache[symbol] = {"data": data, "fetched_at": now}
    return data
