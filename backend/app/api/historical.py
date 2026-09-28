from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.features import IndustrialBaseline
from app.schemas.historical import IndustrialBaselineSchema
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/baselines", response_model=List[IndustrialBaselineSchema])
def get_all_baselines(limit: int = 500, db: Session = Depends(get_db)):
    """Retrieve all historical baselines for industrial sites."""
    baselines = db.query(IndustrialBaseline).limit(limit).all()
    return baselines

@router.get("/sites/{site_id}/thermal-profile", response_model=IndustrialBaselineSchema)
def get_site_thermal_profile(site_id: int, db: Session = Depends(get_db)):
    """Retrieve the historical thermal profile/baseline for a specific industrial site."""
    baseline = db.query(IndustrialBaseline).filter(IndustrialBaseline.site_id == site_id).first()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline for site not found")
    return baseline
