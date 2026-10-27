"""
History & Analytics (spec section 21) — aggregates persisted diagnostic
runs into time-range summaries and simple time series for charting.
"""
from datetime import datetime, time, timedelta, timezone

import numpy as np
import pandas as pd

RANGE_TO_DAYS = {"today": 1, "7d": 7, "30d": 30}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def window_bounds(
    range_key: str,
    start: datetime | None = None,
    end: datetime | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    now = _as_utc(now or datetime.now(timezone.utc))
    if range_key == "custom":
        if start is None or end is None:
            raise ValueError("Custom analytics ranges require both start and end.")
        window_start, window_end = _as_utc(start), _as_utc(end)
    elif range_key == "today" and start is not None and end is not None:
        # The browser supplies local midnight and its current time as UTC instants.
        window_start, window_end = _as_utc(start), _as_utc(end)
    elif range_key == "today":
        utc_now = now
        window_start = datetime.combine(utc_now.date(), time.min, tzinfo=timezone.utc)
        window_end = utc_now
    else:
        window_end = now
        window_start = now - timedelta(days=RANGE_TO_DAYS.get(range_key, 7))

    if window_start > window_end:
        raise ValueError("Analytics range start must be before its end.")
    return window_start, window_end


def _to_dataframe(runs: list) -> pd.DataFrame:
    rows = []
    for run in runs:
        result = run.result_json or {}
        packet_loss = result.get("packet_loss") or {}
        rows.append({
            "created_at": run.created_at,
            "health_score": run.health_score,
            "latency_avg_ms": run.latency_avg_ms,
            # Older rows may have stored 100% when all ICMP probes timed out.
            # Their JSON retains the unavailable flag, so exclude them retroactively.
            "packet_loss_pct": None if packet_loss.get("icmp_unavailable") else run.packet_loss_pct,
            "dns_response_ms": run.dns_response_ms,
            "simulated": bool(result.get("simulated", False)),
        })
    return pd.DataFrame(rows)


def summarize(runs: list, range_key: str = "7d", start: datetime | None = None, end: datetime | None = None) -> dict:
    df = _to_dataframe(runs)
    if df.empty:
        return {"has_data": False, "range": range_key, "series": [], "stats": {}}

    window_start, window_end = window_bounds(range_key, start, end)

    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    mask = (df["created_at"] >= window_start) & (df["created_at"] <= window_end)
    windowed = df.loc[mask]

    if windowed.empty:
        return {"has_data": False, "range": range_key, "series": [], "stats": {}}

    sources = set(windowed["simulated"].tolist())
    stats_source = "mixed" if len(sources) > 1 else ("simulated" if True in sources else "real")

    def stats_for(col):
        series = windowed[col].dropna()
        if series.empty:
            return None
        return {
            "avg": round(float(series.mean()), 2),
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
            "p95": round(float(np.percentile(series, 95)), 2),
        }

    return {
        "has_data": True,
        "range": range_key,
        "stats_source": stats_source,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "stats": {
            "health_score": stats_for("health_score"),
            "latency_avg_ms": stats_for("latency_avg_ms"),
            "packet_loss_pct": stats_for("packet_loss_pct"),
            "dns_response_ms": stats_for("dns_response_ms"),
        },
        "series": [
            {
                "timestamp": row["created_at"].isoformat(),
                "health_score": row["health_score"],
                "latency_avg_ms": row["latency_avg_ms"],
                "packet_loss_pct": row["packet_loss_pct"],
                "dns_response_ms": row["dns_response_ms"],
                "simulated": bool(row["simulated"]),
            }
            for _, row in windowed.sort_values("created_at").iterrows()
        ],
    }


def compare_periods(runs: list, range_key: str = "7d") -> dict:
    """Compare the most recent window against the equally-sized window before it."""
    df = _to_dataframe(runs)
    if df.empty:
        return {"has_data": False}

    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    now = datetime.now(timezone.utc)
    days = RANGE_TO_DAYS.get(range_key, 7)
    recent_start = now - timedelta(days=days)
    prior_start = now - timedelta(days=days * 2)

    recent = df[(df["created_at"] >= recent_start) & (df["created_at"] <= now)]
    prior = df[(df["created_at"] >= prior_start) & (df["created_at"] < recent_start)]
    sources = set(recent["simulated"].tolist()) | set(prior["simulated"].tolist())

    def avg(frame, col):
        series = frame[col].dropna()
        return round(float(series.mean()), 2) if not series.empty else None

    return {
        "has_data": not recent.empty and not prior.empty,
        "stats_source": (
            "mixed" if len(sources) > 1
            else ("simulated" if True in sources else "real")
        ),
        "recent": {
            "health_score": avg(recent, "health_score"), "latency_avg_ms": avg(recent, "latency_avg_ms"),
            "packet_loss_pct": avg(recent, "packet_loss_pct"),
        },
        "prior": {
            "health_score": avg(prior, "health_score"), "latency_avg_ms": avg(prior, "latency_avg_ms"),
            "packet_loss_pct": avg(prior, "packet_loss_pct"),
        },
    }
