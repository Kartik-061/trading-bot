"""
main.py
Entry point. Run with: uvicorn main:app --reload
Then visit http://127.0.0.1:8000/docs for interactive API docs.
"""
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.api.routes import router
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Trading Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={"status": False, "reason": "Invalid request parameters", "details": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": False, "reason": "Internal server error. Check server logs for detail."},
    )


@app.on_event("startup")
def validate_config_on_startup():
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
    return {"status": "ok", "mode": settings.MODE}