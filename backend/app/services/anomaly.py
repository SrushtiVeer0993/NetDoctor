"""
Anomaly detection (spec section 20).

Statistical approach first (moving average + rolling std + z-score against
a trailing baseline) — this is the version actually used by the API.
Isolation Forest (scikit-learn) is available as an optional, explicitly
secondary multivariate detector, per the spec's own ordering: "First
implement statistical detection... optionally implement Isolation Forest
after the statistical version works." Never marketed as "AI diagnosis" —
this is always labeled "Anomaly Detection".
"""
import numpy as np


def statistical_anomalies(values: list[float | None], window: int = 5, z_threshold: float = 2.5) -> list[dict]:
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    results = []
    for pos, (idx, v) in enumerate(clean):
        baseline_vals = [cv for _, cv in clean[max(0, pos - window):pos]]
        if len(baseline_vals) < 3:
            results.append({"index": idx, "value": v, "baseline_mean": None, "baseline_std": None, "z_score": None, "is_anomaly": False})
            continue
        mean = float(np.mean(baseline_vals))
        std = float(np.std(baseline_vals)) or 1e-6
        z = (v - mean) / std
        results.append({
            "index": idx, "value": v, "baseline_mean": round(mean, 2), "baseline_std": round(std, 2),
            "z_score": round(z, 2), "is_anomaly": bool(abs(z) >= z_threshold),
        })
    return results


def isolation_forest_anomalies(rows: list[dict]) -> list[dict] | None:
    """Optional multivariate pass over [latency, packet_loss, dns]. Returns
    None (not an error) when scikit-learn is unavailable or there isn't
    enough history yet — the statistical result above always stands alone."""
    try:
        from sklearn.ensemble import IsolationForest
    except Exception:
        return None

    clean_rows = [
        (i, r) for i, r in enumerate(rows)
        if all(r.get(k) is not None for k in ("latency_avg_ms", "packet_loss_pct", "dns_response_ms"))
    ]
    if len(clean_rows) < 10:
        return None

    X = np.array([[r["latency_avg_ms"], r["packet_loss_pct"], r["dns_response_ms"]] for _, r in clean_rows])
    model = IsolationForest(contamination=0.15, random_state=42)
    preds = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    return [{"index": idx, "is_anomaly": bool(p == -1)} for (idx, _), p in zip(clean_rows, preds)]
