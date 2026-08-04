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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import Base, engine
from app.api.routes import router
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Trading Bot API", version="0.1.0")

# Rate limiting - keyed by IP address. Default limit applies to every route
# unless overridden per-endpoint. This matters most for the yfinance-backed
# endpoints (screener, backtest) - Yahoo Finance itself rate-limits, and a
# runaway client hammering our API could get OUR server's IP blocked by them.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.mount("/dashboard", StaticFiles(directory="frontend", html=True), name="dashboard")


@app.get("/")
def root():
    return {"message": "Trading bot API running. See /docs for API or /dashboard for the UI."}


@app.get("/health")
def health_check():
    """Simple liveness check - useful for Docker healthchecks or a future
    deploy platform (Render, etc) to confirm the app actually booted."""
    return {"status": "ok", "mode": settings.MODE}
