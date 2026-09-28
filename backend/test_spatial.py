from app.models.database import SessionLocal
from app.models.firms import FirmsEvent
from sqlalchemy.sql import func
from sqlalchemy import text

db = SessionLocal()

# Count records
count = db.query(FirmsEvent).count()
print(f"Total FIRMS records: {count}")

if count > 0:
    # Test spatial query: Find points within 100km of the first point
    first_event = db.query(FirmsEvent).first()
    print(f"\nFirst event: ID {first_event.event_id}, Lat: {first_event.latitude}, Lon: {first_event.longitude}")
    print(f"SRID check (from DB): {db.execute(text(f'SELECT ST_SRID(geom::geometry) FROM firms_events WHERE event_id = {first_event.event_id}')).scalar()}")
    
    # 100,000 meters = 100 km
    nearby = db.query(FirmsEvent).filter(
        func.ST_DWithin(FirmsEvent.geom, first_event.geom, 100000)
    ).all()
    print(f"Found {len(nearby)} events within 100km of the first event (including itself).")

db.close()
