"""
complexes.py — Phase 7: Facility-complex API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.facility_cluster import FacilityComplex, FacilityHysteresisState
from app.services.hysteresis_service import get_complex_state, HYSTERESIS_CLEAR_DAYS
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
def list_facility_complexes(limit: int = 500, db: Session = Depends(get_db)):
    """List all DBSCAN-clustered facility complexes with their hysteresis state."""
    complexes = db.query(FacilityComplex).limit(limit).all()
    results = []
    for fc in complexes:
        state_info = get_complex_state(db, fc.complex_id)
        results.append({
            "complex_id": fc.complex_id,
            "name": fc.name,
            "facility_type": fc.facility_type,
            "member_count": fc.member_count,
            "centroid_lat": fc.centroid_lat,
            "centroid_lon": fc.centroid_lon,
            "radius_m": fc.radius_m,
            "source": fc.source,
            "hysteresis": state_info,
        })
    return results


@router.get("/geojson")
def facility_complexes_geojson(db: Session = Depends(get_db)):
    """Return facility complexes as GeoJSON for the map layer."""
    complexes = db.query(FacilityComplex).all()
    features = []
    for fc in complexes:
        if fc.centroid_lat is None or fc.centroid_lon is None:
            continue
        state_info = get_complex_state(db, fc.complex_id)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [fc.centroid_lon, fc.centroid_lat],
            },
            "properties": {
                "complex_id": fc.complex_id,
                "name": fc.name,
                "facility_type": fc.facility_type,
                "member_count": fc.member_count,
                "radius_m": fc.radius_m,
                "hysteresis_state": state_info["state"],
                "clear_days_streak": state_info["clear_days_streak"],
                "clear_days_required": HYSTERESIS_CLEAR_DAYS,
                "total_abnormal_events": state_info["total_abnormal_events"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/{complex_id}/state")
def get_hysteresis_state(complex_id: int, db: Session = Depends(get_db)):
    """Return the full hysteresis state for a specific facility complex."""
    fc = db.query(FacilityComplex).filter(FacilityComplex.complex_id == complex_id).first()
    if not fc:
        raise HTTPException(status_code=404, detail="Facility complex not found")
    return {
        "complex": {
            "complex_id": fc.complex_id,
            "name": fc.name,
            "facility_type": fc.facility_type,
            "centroid_lat": fc.centroid_lat,
            "centroid_lon": fc.centroid_lon,
        },
        "hysteresis": get_complex_state(db, complex_id),
    }
