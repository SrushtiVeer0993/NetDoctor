"""
Speed test service (spec section 9).

IMPORTANT (per spec): this is a plain HTTP download/upload against a
public test endpoint. It is explicitly NOT presented as equivalent to a
commercial ISP speed test (Ookla etc.) — every result carries a
`methodology` string saying exactly what was measured, and the frontend
must display it rather than a bare number.
"""
import os
import statistics
import time

import requests

# Cloudflare's public speed-test backend serves arbitrary-size bodies and
# accepts uploads without auth — a reasonable, dependency-free target for
# an educational measurement. If unreachable, the test fails cleanly with
# "Unavailable on this system" rather than fabricating a number.
DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes={size}"
UPLOAD_URL = "https://speed.cloudflare.com/__up"

METHODOLOGY = (
    "Three single-stream HTTP transfers to Cloudflare speed test endpoints; "
    "download and upload report the median measured Mbps. Latency is an "
    "unloaded ICMP measurement; jitter is mean consecutive-ping variation. "
    "This is an estimate, not a multi-connection ISP speed test."
)
RUNS = 3


def _mbps(bytes_transferred: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    bits = bytes_transferred * 8
    return round((bits / seconds) / 1_000_000, 2)


def measure_download(size_bytes: int = 10_000_000, session=None) -> dict:
    try:
        start = time.perf_counter()
        client = session or requests
        resp = client.get(
            DOWNLOAD_URL.format(size=size_bytes), timeout=30, stream=True,
            headers={"Accept-Encoding": "identity"},
        )
        try:
            resp.raise_for_status()
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
            elapsed = time.perf_counter() - start
            if total != size_bytes:
                raise IOError(f"Expected {size_bytes} download bytes, received {total}.")
            return {"success": True, "bytes": total, "seconds": elapsed, "mbps": _mbps(total, elapsed)}
        finally:
            resp.close()
    except Exception as exc:
        return {"success": False, "error": str(exc), "mbps": None}


def measure_upload(size_bytes: int = 5_000_000, session=None) -> dict:
    try:
        payload = os.urandom(size_bytes)
        start = time.perf_counter()
        client = session or requests
        response = client.post(UPLOAD_URL, data=payload, timeout=30)
        try:
            response.raise_for_status()
        finally:
            response.close()
        elapsed = time.perf_counter() - start
        return {"success": True, "bytes": size_bytes, "seconds": round(elapsed, 2), "mbps": _mbps(size_bytes, elapsed)}
    except Exception as exc:
        return {"success": False, "error": str(exc), "mbps": None}


def measure_latency_jitter(host: str = "1.1.1.1") -> dict:
    from app.services.legacy_diagnostics import measure_latency
    result = measure_latency(host, count=6)
    samples = result.get("samples", [])
    jitter = (
        sum(abs(right - left) for left, right in zip(samples, samples[1:]))
        / (len(samples) - 1)
        if len(samples) > 1 else None
    )
    return {"avg_ms": result["avg_ms"], "jitter_ms": round(jitter, 1) if jitter is not None else None}


def run_speed_test(download_bytes: int = 10_000_000, upload_bytes: int = 5_000_000) -> dict:
    with requests.Session() as session:
        download_runs = _run_transfer_runs(measure_download, download_bytes, session)
        upload_runs = _run_transfer_runs(measure_upload, upload_bytes, session)
    download = _summarize_runs(download_runs)
    upload = _summarize_runs(upload_runs)
    latency = measure_latency_jitter()
    return {
        "methodology": METHODOLOGY,
        "source": "backend_runtime",
        "download": download,
        "upload": upload,
        "latency_ms": latency["avg_ms"],
        "jitter_ms": latency["jitter_ms"],
    }


def _run_transfer_runs(measure, size_bytes: int, session) -> list[dict]:
    runs = []
    for _ in range(RUNS):
        result = measure(size_bytes, session)
        runs.append(result)
        if not result.get("success"):
            break
    return runs


def _summarize_runs(runs: list[dict]) -> dict:
    failed = [run for run in runs if not run.get("success")]
    if failed:
        return {
            "success": False, "mbps": None,
            "error": "; ".join(run.get("error", "Transfer failed") for run in failed),
            "samples_mbps": [run["mbps"] for run in runs if run.get("success")],
        }
    rates = [run["mbps"] for run in runs]
    seconds = [run["seconds"] for run in runs]
    return {
        "success": True,
        "bytes": runs[0]["bytes"],
        "seconds": round(statistics.median(seconds), 3),
        "mbps": round(statistics.median(rates), 2),
        "samples_mbps": [round(rate, 2) for rate in rates],
    }
