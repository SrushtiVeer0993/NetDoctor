"""
Importing this package registers every model on Base.metadata, so
`Base.metadata.create_all()` (main.py, Phase 1 fast-start) and Alembic's
autogenerate both see the full schema regardless of which API module
happens to import which model first.
"""
from app.models import (  # noqa: F401
    alert,
    device,
    diagnostic,
    monitoring,
    report,
    settings,
    speedtest,
    traceroute,
    user,
)
