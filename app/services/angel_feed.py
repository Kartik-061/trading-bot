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
import time
from datetime import datetime, timedelta

import requests

from app.config import settings
from app.cache import ttl_cache

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


_nifty_token = None
_nifty_lookup_attempted = False


def get_nifty_token():
    """Best-effort lookup of the Nifty 50 index's token, for relative-
    strength comparisons in the long-term screener. Index rows in Angel's
    instrument master don't have the "-EQ" suffix _build_symbol_token_map()
    filters for, so this searches separately. NOT live-verified against
    Angel's real instrument master (no network access to angelone.in from
    this sandbox) - matches by name text rather than a specific
    instrumenttype code, since that exact value couldn't be confirmed
    here. Returns None (not an exception) if no confident match is found,
    so a broken lookup degrades to "skip relative strength" rather than
    crashing the scan - same contract fetch_index_baseline() already has
    for yfinance."""
    global _nifty_token, _nifty_lookup_attempted
    if _nifty_lookup_attempted:
        return _nifty_token
    _nifty_lookup_attempted = True
    try:
        instruments = _load_instrument_master()
        for row in instruments:
            if row.get("exch_seg") != "NSE":
                continue
            name = str(row.get("name", "")).upper()
            symbol_field = str(row.get("symbol", "")).upper()
            if name in ("NIFTY", "NIFTY 50") or symbol_field in ("NIFTY", "NIFTY50", "NIFTY 50"):
                _nifty_token = row.get("token")
                logger.info(f"Angel Nifty 50 index token found: {_nifty_token}")
                return _nifty_token
        logger.warning("Could not find a confident Nifty 50 index match in Angel's instrument master - relative strength will be skipped.")
    except Exception as e:
        logger.warning(f"Nifty 50 index token lookup failed (non-fatal, relative strength will be skipped): {e}")
    return None


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


_PERIOD_TO_DAYS = {
    "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "60d": 60, "90d": 90,
    "1y": 365, "2y": 730, "5y": 1825,
    "max": 3650,  # Angel has no true "max" like yfinance - 10y is a practical stand-in
}


_CANDLE_MAX_RETRIES = 3
_CANDLE_BACKOFF_SECONDS = [3, 8, 20]


def _call_candle_data_with_retry(api, params: dict, symbol: str) -> dict:
    """Angel's historical-data endpoint has its own separate rate limit from
    ltpData's - hit this live: 'Access denied because of exceeding access
    rate' comes back as raw text, not JSON, which SmartApi's own library
    can't parse and raises as DataException (an exception, not a
    success:False dict like the auth-error case) - so it needs its own
    except block, not just a resp.get() check."""
    from SmartApi.smartExceptions import DataException

    last_error = None
    for attempt in range(_CANDLE_MAX_RETRIES):
        try:
            return api.getCandleData(params)
        except DataException as e:
            last_error = e
            if attempt < _CANDLE_MAX_RETRIES - 1:
                wait = _CANDLE_BACKOFF_SECONDS[attempt]
                logger.warning(
                    f"Angel getCandleData rate-limited fetching {symbol} "
                    f"(attempt {attempt + 1}/{_CANDLE_MAX_RETRIES}), waiting {wait}s: {e}"
                )
                time.sleep(wait)
    raise RuntimeError(
        f"Angel One's historical-data API rate-limited {symbol} after {_CANDLE_MAX_RETRIES} retries. "
        f"Try again in a minute, or fewer chart requests back-to-back. Original error: {last_error}"
    )


@ttl_cache(ttl_seconds=900)
def get_angel_ohlc(symbol: str, period: str = "1y") -> list:
    """Daily OHLC candles via Angel One's getCandleData - same output shape
    ({time, open, high, low, close}, Lightweight-Charts-ready) as
    historical_data.fetch_ohlc_for_chart, so it's a drop-in for the
    /discover/stock-chart endpoint.

    NOT live-tested against Angel's real servers (no network access to
    angelone.in from this sandbox) - verify a couple of periods actually
    render correctly before relying on this."""
    tradingsymbol, token = _get_token(symbol)
    return _get_ohlc_by_token(token, period=period, label=symbol)


def _get_ohlc_by_token(token: str, period: str = "1y", label: str = "") -> list:
    """Same as get_angel_ohlc but takes a raw Angel symboltoken directly,
    for instruments (like the Nifty 50 index) that aren't in the
    equity-only symbol map _get_token() looks up."""
    days = _PERIOD_TO_DAYS.get(period, 365)
    todate = datetime.utcnow()
    fromdate = todate - timedelta(days=days)
    params = {
        "exchange": "NSE",
        "symboltoken": token,
        "interval": "ONE_DAY",
        "fromdate": fromdate.strftime("%Y-%m-%d %H:%M"),
        "todate": todate.strftime("%Y-%m-%d %H:%M"),
    }

    api = _get_session()
    resp = _call_candle_data_with_retry(api, params, label or token)

    if not _is_success(resp) and _is_auth_error(resp):
        logger.warning(f"Angel session looks invalid/expired fetching OHLC for {label or token}, re-logging in and retrying once.")
        _reset_session()
        api = _get_session()
        resp = _call_candle_data_with_retry(api, params, label or token)

    if not _is_success(resp):
        raise RuntimeError(f"Angel getCandleData failed for {label or token}: {resp}")

    rows = resp.get("data") or []
    if not rows:
        raise ValueError(f"No historical data for {label or token} at period={period} (Angel returned an empty candle set)")

    candles = []
    for row in rows:
        ts_str, o, h, l, c = row[0], row[1], row[2], row[3], row[4]
        # Angel's timestamps come back as ISO 8601 with an offset, e.g.
        # "2021-02-10T09:15:00+05:30" - fromisoformat handles that natively.
        ts = datetime.fromisoformat(ts_str)
        candles.append({
            "time": int(ts.timestamp()),
            "open": round(float(o), 2),
            "high": round(float(h), 2),
            "low": round(float(l), 2),
            "close": round(float(c), 2),
        })
    return candles


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


def get_angel_ltp_bulk(symbols: list) -> dict:
    """Fetch LTP for MANY symbols in a single Angel API call, via
    getMarketData - up to 50 symbols per call, rate-limited at 1 request/
    second for this endpoint (vs. 1 rps for getLtpData too, but that's
    1 rps PER SYMBOL if called individually - this is 1 rps for the whole
    batch). Call this ONCE per tick instead of looping get_angel_ltp() per
    symbol, and every result gets written into the same _price_cache
    get_angel_ltp() reads from - so any code still calling get_angel_ltp()
    per-symbol afterward just hits cache, no extra requests.

    Returns {symbol: data_dict} for symbols that were fetched successfully;
    a symbol missing from the result (couldn't find its token, or Angel's
    response didn't include it) is simply absent from the returned dict -
    callers should handle that as "no fresh price this tick", not raise.

    NOT live-tested against Angel's real servers - the exact response
    field names for FULL mode are inferred from SmartAPI forum examples,
    not independently verified here."""
    if not symbols:
        return {}

    tokens_to_symbol = {}
    for sym in symbols:
        try:
            _, token = _get_token(sym)
            tokens_to_symbol[token] = sym
        except KeyError as e:
            logger.warning(f"Skipping {sym} in bulk LTP fetch: {e}")

    if not tokens_to_symbol:
        return {}

    results = {}
    token_list = list(tokens_to_symbol.keys())
    # getMarketData caps out around 50 tokens per call per Angel's docs -
    # chunk defensively in case the watchlist ever grows past that.
    for i in range(0, len(token_list), 50):
        chunk = token_list[i:i + 50]
        params = {"mode": "FULL", "exchangeTokens": {"NSE": chunk}}

        api = _get_session()
        try:
            resp = api.getMarketData(params["mode"], params["exchangeTokens"])
        except Exception as e:
            logger.warning(f"Angel getMarketData bulk fetch failed for a chunk of {len(chunk)} symbols: {e}")
            continue

        if not _is_success(resp) and _is_auth_error(resp):
            logger.warning("Angel session looks invalid/expired for bulk LTP fetch, re-logging in and retrying once.")
            _reset_session()
            api = _get_session()
            try:
                resp = api.getMarketData(params["mode"], params["exchangeTokens"])
            except Exception as e:
                logger.warning(f"Angel getMarketData retry also failed: {e}")
                continue

        if not _is_success(resp):
            logger.warning(f"Angel getMarketData bulk fetch returned failure: {resp}")
            continue

        fetched = (resp.get("data") or {}).get("fetched") or []
        now = datetime.utcnow()
        for row in fetched:
            token = str(row.get("symbolToken", ""))
            sym = tokens_to_symbol.get(token)
            if not sym:
                continue
            last_price = float(row.get("ltp", 0))
            prev_close = float(row.get("close", last_price)) if row.get("close") else last_price
            data = {
                "symbol": sym,
                "last_price": round(last_price, 2),
                "previous_close": round(prev_close, 2),
                "day_high": round(float(row.get("high", last_price)), 2),
                "day_low": round(float(row.get("low", last_price)), 2),
                "change_pct": round((last_price - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
                "fetched_at": now.isoformat(),
            }
            results[sym] = data
            _price_cache[sym] = {"data": data, "fetched_at": now}

        unfetched = (resp.get("data") or {}).get("unfetched") or []
        logger.info(
            f"Angel bulk LTP fetch: {len(fetched)} fetched, {len(unfetched)} unfetched, "
            f"chunk of {len(chunk)} requested. Sample: {[r.get('tradingSymbol') for r in fetched[:3]]}"
        )

    return results
