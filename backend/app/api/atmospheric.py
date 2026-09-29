"""
atmospheric.py — Phase 7: Atmospheric anomaly API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.services.atmospheric_service import AtmosphericReading, AtmosphericBaseline, analyze_atmospheric_anomaly
from app.models.features import FusedEventScore
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/readings/geojson")
def atmospheric_readings_geojson(db: Session = Depends(get_db)):
    """
    Return atmospheric anomaly readings as GeoJSON for the map overlay layer.
    Only returns readings where is_anomalous = 1.
    """
    from app.models.facility_cluster import FacilityComplex
    anomalous = db.query(AtmosphericReading).filter(
        AtmosphericReading.is_anomalous == 1
    ).all()

    features = []
    for reading in anomalous:
        fc = db.query(FacilityComplex).filter(
            FacilityComplex.complex_id == reading.complex_id
        ).first()
        if not fc or fc.centroid_lat is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [fc.centroid_lon, fc.centroid_lat],
            },
            "properties": {
                "complex_id": reading.complex_id,
                "complex_name": fc.name,
                "gas_species": reading.gas_species,
                "column_value": reading.column_value,
                "z_score": reading.z_score,
                "measurement_date": reading.measurement_date,
                "alert_type": "NON-THERMAL ATMOSPHERIC ANOMALY",
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/complex/{complex_id}")
def get_complex_atmospheric_history(complex_id: int, db: Session = Depends(get_db)):
    """Return all atmospheric readings for a facility complex, grouped by gas species."""
    readings = db.query(AtmosphericReading).filter(
        AtmosphericReading.complex_id == complex_id
    ).order_by(AtmosphericReading.measurement_date.desc()).limit(100).all()

    if not readings:
        return {"complex_id": complex_id, "readings": [], "has_data": False}

    by_gas = {}
    for r in readings:
        g = r.gas_species
        if g not in by_gas:
            by_gas[g] = []
        by_gas[g].append({
            "date": r.measurement_date,
            "value": r.column_value,
            "z_score": r.z_score,
            "is_anomalous": bool(r.is_anomalous),
            "qa_value": r.qa_value,
        })
    return {"complex_id": complex_id, "readings_by_gas": by_gas, "has_data": True}


@router.get("/fused/{event_id}")
def get_fused_score(event_id: int, db: Session = Depends(get_db)):
    """Return the fused thermal+atmospheric confidence score for an event."""
    score = db.query(FusedEventScore).filter(
        FusedEventScore.event_id == event_id
    ).first()
    if not score:
        return {
            "event_id": event_id,
            "fused_score": None,
            "signal_agreement": "UNKNOWN",
            "alert_category": None,
            "explanation": "No atmospheric data computed for this event yet.",
        }
    return {
        "event_id": event_id,
        "fused_score": score.fused_score,
        "signal_agreement": score.signal_agreement,
        "alert_category": score.alert_category,
        "explanation": score.explanation,
        "atmos_max_z": score.atmos_max_z,
        "computed_at": score.computed_at,
    }
