"""
main.py
Entry point. Run with: uvicorn main:app --reload
Then visit http://127.0.0.1:8000/docs for interactive API docs (auto-generated,
same idea as DRF's browsable API on BookIQ).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.api.routes import router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Trading Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev; tighten before deploying anywhere real
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.mount("/dashboard", StaticFiles(directory="frontend", html=True), name="dashboard")


@app.get("/")
def root():
    return {"message": "Trading bot API running. See /docs for API or /dashboard for the UI."}
