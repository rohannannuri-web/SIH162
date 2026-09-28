from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.services.satellite_service import analyze_satellite_context

router = APIRouter(tags=["satellite"])

@router.get("/{event_id}")
def get_satellite_analysis(event_id: int, db: Session = Depends(get_db)):
    result = analyze_satellite_context(db, event_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result

@router.post("/analyze/{event_id}")
def run_satellite_analysis(event_id: int, db: Session = Depends(get_db)):
    result = analyze_satellite_context(db, event_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result
