"""
NetDoctor backend entry point.

All 9 phases from the project spec are wired in below. See
/docs/architecture.md for what each phase covers and the module each one
lives in. Nothing fakes data outside of DEMO_MODE (settings.DEMO_MODE or a
per-request `?demo=true`) — see app.services.demo_data and
app.api.deps.resolve_demo_mode.
"""
from contextlib import asynccontextmanager
import os

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api import (
    alerts,
    analytics,
    auth,
    dashboard,
    diagnostics,
    monitoring,
    network,
    packets,
    reports,
    settings as settings_api,
    speedtest,
)
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


def _upgrade_database_schema():
    alembic_ini = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config = Config(alembic_ini)
    existing_tables = set(inspect(engine).get_table_names())
    if existing_tables and "alembic_version" not in existing_tables:
        required = {"users", "diagnostic_runs", "monitoring_sessions", "monitoring_measurements"}
        if not required.issubset(existing_tables):
            raise RuntimeError(
                "Database has an unversioned partial schema; reconcile it before applying migrations."
            )
        command.stamp(config, "0002")
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _upgrade_database_schema()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="NetDoctor API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "demo_mode": settings.DEMO_MODE}


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(diagnostics.router)
app.include_router(network.router)
app.include_router(speedtest.router)
app.include_router(monitoring.router)
app.include_router(alerts.router)
app.include_router(packets.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(settings_api.router)
