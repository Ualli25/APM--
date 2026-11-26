"""FastAPI entry point for the Academic Council Secretary system."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database.db import init_db
from app.database.seed import migrate_legacy_database, seed_data
from app.routers import items, meetings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not getattr(_app.state, "skip_startup", False):
        init_db()
        migrate_legacy_database()
        seed_data()
    yield


app = FastAPI(
    title="АРМ секретаря Учёного совета",
    description="REST API для учёта советов, соискателей, диссертаций и заседаний.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(items.router)
app.include_router(meetings.router)
app.mount(
    "/mobile",
    StaticFiles(directory=Path(__file__).resolve().parents[1] / "mobile_app", html=True),
    name="mobile-app",
)


@app.get("/", tags=["Система"])
def root():
    return {"message": "АРМ секретаря Учёного совета работает", "docs": "/docs"}


@app.get("/health", tags=["Система"])
def health():
    return {"status": "ok"}
