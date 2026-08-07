"""
main.py
Entry point. Run with: uvicorn main:app --reload
Then visit http://127.0.0.1:8000/docs for interactive API docs (auto-generated,
same idea as DRF's browsable API on BookIQ).
"""
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.rate_limit import limiter

from app.database import Base, engine
from app.api.routes import router
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Trading Bot API", version="0.1.0")

# Rate limiting - explicit @limiter.limit() decorators are applied to the
# expensive, Yahoo-Finance-backed endpoints in routes.py. A router-level
# auth dependency breaks slowapi's automatic default_limits mechanism (a
# known interaction quirk), so explicit per-route decorators are used
# instead - verified working even with the auth dependency present.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev; tighten before deploying anywhere real
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Bad query params (wrong type, out of range, etc) get a clean, honest
    400 with the real reason - not FastAPI's default verbose error dump,
    and not a generic unhandled 500 either."""
    errors = [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={"status": False, "reason": "Invalid request parameters", "details": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches anything that slips through a route without its own
    try/except. Logs the real error server-side, but never leaks a raw
    traceback to the client - same principle applies whether this is
    running on localhost or deployed somewhere real."""
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": False, "reason": "Internal server error. Check server logs for detail."},
    )


@app.on_event("startup")
def validate_config_on_startup():
    """Fail loud and immediately if BOT_MODE=live is set without real
    Angel One credentials - better to crash at startup with a clear message
    than silently fail on the first real trade attempt."""
    if settings.MODE == "live":
        try:
            settings.validate_for_live()
            logger.info("Config check passed: LIVE mode credentials present.")
        except RuntimeError as e:
            logger.error(f"STARTUP CONFIG ERROR: {e}")
            raise
    else:
        logger.info(f"Config check passed: running in {settings.MODE.upper()} mode.")


app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Trading bot API running. See /docs for API or /dashboard for the UI."}


@app.get("/health")
def health_check():
    """Simple liveness check - useful for Docker healthchecks or a future
    deploy platform (Render, etc) to confirm the app actually booted."""
    return {"status": "ok", "mode": settings.MODE}

@app.on_event("startup")
async def auto_start_bot():
    """
    Render restarts (redeploys, crashes, free-tier spin-down/wake) reset
    BotRunner's in-memory state to stopped. Without this, every restart
    silently kills paper-trading data collection until someone notices
    and manually calls /bot/start again - which already happened once
    today. This makes the bot self-healing instead.
    """
    import logging
    logger = logging.getLogger("startup")
    try:
        result = bot_runner.start(strategy_name="mean_reversion")
        if result.get("status"):
            logger.info(f"Auto-started bot on boot: session_id={result.get('session_id')}")
        else:
            logger.info(f"Bot auto-start skipped: {result.get('reason')}")
    except Exception as e:
        logger.exception(f"Bot auto-start failed: {e}")