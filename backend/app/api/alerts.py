from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.alert import Alert
from app.services.alert_service import trigger_all_alerts

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/")
def get_all_alerts(limit: int = 100, db: Session = Depends(get_db)):
    """Retrieve all active alerts."""
    alerts = db.query(Alert).filter(Alert.is_active == True).order_by(Alert.timestamp.desc()).limit(limit).all()
    return alerts

@router.post("/evaluate")
def run_alert_evaluation(db: Session = Depends(get_db)):
    """Trigger alert evaluation for all events (prototype utility)."""
    trigger_all_alerts(db)
    return {"message": "Alert evaluation completed successfully."}
