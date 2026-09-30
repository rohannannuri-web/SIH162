"""
unregistered.py — Phase 6 + 8: Unregistered activity API endpoints
===================================================================
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.services.unregistered_service import (
    get_unregistered_geojson,
    get_unregistered_summary,
)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/geojson")
def unregistered_geojson(db: Session = Depends(get_db)):
    """
    Return all UNREGISTERED_ACTIVITY alerts as GeoJSON for the frontend map layer.
    Each feature has: alert_type, priority, fused_score, explanation.
    """
    return get_unregistered_geojson(db)


@router.get("/summary")
def unregistered_summary(db: Session = Depends(get_db)):
    """Return count breakdown by unregistered alert category."""
    return get_unregistered_summary(db)


@router.get("/brick-kiln-zones")
def brick_kiln_zones():
    """
    Return the Indo-Gangetic Plains brick kiln belt bounding box and active months.
    Used by the frontend to overlay the seasonal suppression zone.
    """
    from app.services.gem_service import BRICK_KILN_BELT
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [BRICK_KILN_BELT["lon_min"], BRICK_KILN_BELT["lat_min"]],
                [BRICK_KILN_BELT["lon_max"], BRICK_KILN_BELT["lat_min"]],
                [BRICK_KILN_BELT["lon_max"], BRICK_KILN_BELT["lat_max"]],
                [BRICK_KILN_BELT["lon_min"], BRICK_KILN_BELT["lat_max"]],
                [BRICK_KILN_BELT["lon_min"], BRICK_KILN_BELT["lat_min"]],
            ]],
        },
        "properties": {
            "name": "Indo-Gangetic Plains Brick Kiln Belt",
            "active_months": sorted(list(BRICK_KILN_BELT["active_months"])),
            "note": (
                "Thermal detections within this zone during active months (Oct-Jun) "
                "are attributed to seasonal brick kiln firing and not escalated as "
                "unregistered industrial activity. Source: Guttikunda et al. (2013)."
            ),
        },
    }
