from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.features import EventFeature
from app.schemas.classification import EventFeatureSchema
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

CLASS_MAPPING = {
    0: "Natural/Forest Fire",
    1: "Agricultural Burning",
    2: "Persistent Industrial Thermal Source",
    3: "Abnormal Industrial Thermal Event",
    -1: "Unknown / Insufficient Evidence"
}

@router.get("/", response_model=List[EventFeatureSchema])
def get_all_classifications(limit: int = 250, db: Session = Depends(get_db)):
    """Retrieve all event features and their ml_class predictions."""
    features = db.query(EventFeature).limit(limit).all()
    return features

@router.get("/{event_id}", response_model=EventFeatureSchema)
def get_classification_by_event(event_id: int, db: Session = Depends(get_db)):
    """Retrieve classification features and result for a specific event."""
    feature = db.query(EventFeature).filter(EventFeature.event_id == event_id).first()
    if not feature:
        raise HTTPException(status_code=404, detail="Classification for event not found")
    return feature

@router.get("/{event_id}/explain")
def explain_classification(event_id: int, db: Session = Depends(get_db)):
    """Returns a human-readable explanation of the classification for the dashboard."""
    feature = db.query(EventFeature).filter(EventFeature.event_id == event_id).first()
    if not feature:
        raise HTTPException(status_code=404, detail="Event not found")
        
    class_id = feature.ml_class
    class_name = CLASS_MAPPING.get(class_id, "Unknown")
    
    risk = "LOW"
    if class_id == 3:
        risk = "HIGH"
    elif class_id == 1 or class_id == 0:
        risk = "MEDIUM"
        
    evidence = []
    if feature.distance_to_industry_m is not None and feature.distance_to_industry_m < 2000:
        evidence.append(f"Near industrial facility ({feature.distance_to_industry_m:.0f}m)")
    if feature.historical_event_count > 10:
        evidence.append(f"Persistent historical thermal source ({feature.historical_event_count} events)")
    if feature.frp_ratio_to_baseline > 2.0:
        evidence.append(f"FRP is {feature.frp_ratio_to_baseline:.1f}x the historical median")
    if feature.robust_frp_z > 2.5:
        evidence.append(f"Significant thermal abnormality (Z-score: {feature.robust_frp_z:.2f})")
    if feature.dominant_landcover:
        evidence.append(f"Land cover context is {feature.dominant_landcover}")
        
    return {
        "event_id": feature.event_id,
        "classification": class_name,
        "class_id": class_id,
        "risk": risk,
        "evidence": evidence,
        "shap_values": feature.shap_json
    }
