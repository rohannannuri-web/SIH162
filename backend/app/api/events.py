from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.firms import FirmsEvent
from app.schemas.event import FirmsEvent as FirmsEventSchema
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[FirmsEventSchema])
def get_all_events(limit: int = 100, db: Session = Depends(get_db)):
    """Retrieve all FIRMS events, limited by default to 100."""
    events = db.query(FirmsEvent).limit(limit).all()
    return events

@router.get("/geojson")
def get_events_geojson(db: Session = Depends(get_db)):
    """Returns FIRMS events as a GeoJSON FeatureCollection."""
    events = db.query(FirmsEvent).all()
    features = []
    for event in events:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [event.longitude, event.latitude]
            },
            "properties": {
                "event_id": event.event_id,
                "acquisition_time": event.acquisition_time.isoformat() if event.acquisition_time else None,
                "frp": event.frp,
                "confidence": event.confidence,
                "satellite": event.satellite,
                "distance_to_industrial": event.distance_to_industrial,
                "land_cover_class": event.land_cover_class
            }
        })
    return {
        "type": "FeatureCollection",
        "features": features
    }

@router.get("/{event_id}", response_model=FirmsEventSchema)
def get_event_by_id(event_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific FIRMS event by ID."""
    event = db.query(FirmsEvent).filter(FirmsEvent.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
