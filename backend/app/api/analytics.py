from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.diagnostic import DiagnosticRun
from app.models.user import User
from app.services import analytics as engine
from app.services import anomaly

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _user_runs(
    db: Session,
    user: User,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
):
    query = db.query(DiagnosticRun).filter(DiagnosticRun.user_id == user.id)
    if start is not None:
        query = query.filter(DiagnosticRun.created_at >= start)
    if end is not None:
        query = query.filter(DiagnosticRun.created_at <= end)
    query = query.order_by(DiagnosticRun.created_at.desc())
    if limit is not None:
        query = query.limit(limit)
    # A limit, when requested, keeps the most recent rows; consumers get ascending order.
    return list(reversed(query.all()))


@router.get("")
def get_analytics(
    range: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        window_start, window_end = engine.window_bounds(range, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    runs = _user_runs(db, user, start=window_start, end=window_end)
    return engine.summarize(runs, range_key=range, start=window_start, end=window_end)


@router.get("/compare")
def compare(range: str = "7d", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    days = engine.RANGE_TO_DAYS.get(range, 7)
    now = datetime.now(timezone.utc)
    runs = _user_runs(db, user, start=now - timedelta(days=days * 2), end=now)
    return engine.compare_periods(runs, range_key=range)


@router.get("/anomalies")
def get_anomalies(
    metric: str = Query("latency_avg_ms", pattern="^(latency_avg_ms|packet_loss_pct|dns_response_ms)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runs = _user_runs(db, user, limit=500)
    if not runs:
        return {"has_data": False, "statistical": [], "isolation_forest": None, "sources": []}

    values = [getattr(r, metric) for r in runs]
    statistical = anomaly.statistical_anomalies(values)

    rows = [{
        "latency_avg_ms": r.latency_avg_ms, "packet_loss_pct": r.packet_loss_pct,
        "dns_response_ms": r.dns_response_ms,
    } for r in runs]
    iso = anomaly.isolation_forest_anomalies(rows)

    timestamps = [r.created_at.isoformat() for r in runs]
    return {
        "has_data": True, "metric": metric, "timestamps": timestamps,
        "sources": [bool((run.result_json or {}).get("simulated", False)) for run in runs],
        "statistical": statistical, "isolation_forest": iso,
    }
