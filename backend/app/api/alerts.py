from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.alert import AlertEvent
from app.models.user import User

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(limit: int = Query(default=50, ge=1, le=200), unacknowledged_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(AlertEvent).filter(AlertEvent.user_id == user.id)
    if unacknowledged_only:
        q = q.filter(AlertEvent.acknowledged == False)  # noqa: E712
    events = q.order_by(AlertEvent.triggered_at.desc(), AlertEvent.id.desc()).limit(limit).all()
    return [
        {"id": e.id, "triggered_at": e.triggered_at, "metric": e.metric, "current_value": e.current_value,
         "baseline_value": e.baseline_value, "message": e.message, "acknowledged": e.acknowledged}
        for e in events
    ]


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.query(AlertEvent).filter(AlertEvent.id == alert_id, AlertEvent.user_id == user.id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    event.acknowledged = True
    db.commit()
    return {"acknowledged": True}
