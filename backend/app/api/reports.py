import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.diagnostic import DiagnosticRun
from app.models.report import Report
from app.models.user import User
from app.services import reports as engine

router = APIRouter(prefix="/api/reports", tags=["reports"])

REPORTS_DIR = os.path.join(tempfile.gettempdir(), "netdoctor_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def _get_run(db: Session, user: User, run_id: int) -> DiagnosticRun:
    run = db.query(DiagnosticRun).filter(DiagnosticRun.id == run_id, DiagnosticRun.user_id == user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Diagnostic run not found")
    return run


@router.post("/{run_id}/{fmt}")
def generate_report(run_id: int, fmt: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if fmt not in ("pdf", "csv", "json"):
        raise HTTPException(status_code=400, detail="format must be pdf, csv, or json")

    run = _get_run(db, user, run_id)
    filename = f"netdoctor_report_{run_id}_{user.id}.{fmt}"
    path = os.path.join(REPORTS_DIR, filename)

    if fmt == "pdf":
        engine.generate_pdf(run, user, path)
    elif fmt == "csv":
        engine.generate_csv(run, path)
    else:
        engine.generate_json(run, path)

    report = Report(user_id=user.id, diagnostic_run_id=run.id, format=fmt, file_path=path)
    db.add(report)
    db.commit()
    db.refresh(report)

    return {"report_id": report.id, "format": fmt, "download_url": f"/api/reports/{report.id}/download"}


@router.get("/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id, Report.user_id == user.id).first()
    if not report or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Report not found")
    media_types = {"pdf": "application/pdf", "csv": "text/csv", "json": "application/json"}
    return FileResponse(report.file_path, media_type=media_types[report.format], filename=os.path.basename(report.file_path))


@router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    reports = (
        db.query(Report)
        .filter(Report.user_id == user.id)
        .order_by(Report.id.desc())
        .limit(100)
        .all()
    )
    return [
        {"id": r.id, "created_at": r.created_at, "format": r.format,
         "diagnostic_run_id": r.diagnostic_run_id, "download_url": f"/api/reports/{r.id}/download"}
        for r in reports
    ]
