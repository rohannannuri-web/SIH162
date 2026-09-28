from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.firms import FirmsEvent

def calculate_distance_to_industrial(db: Session):
    """
    Uses PostGIS ST_Distance to find the nearest industrial site for each FIRMS event.
    Updates the distance_to_industrial column.
    """
    print("Calculating distance to nearest industrial infrastructure...")
    
    # We use a raw SQL update query to efficiently calculate nearest neighbor distances
    # for all events that don't have it calculated yet.
    # We use a lateral join to find the closest industrial site.
    
    sql = """
    UPDATE firms_events
    SET distance_to_industrial = closest.dist
    FROM (
        SELECT e.event_id, 
               (
                   SELECT ST_Distance(e.geom, i.geometry::geography) 
                   FROM industrial_sites i 
                   ORDER BY e.geom <-> i.geometry::geography 
                   LIMIT 1
               ) as dist
        FROM firms_events e
    ) AS closest
    WHERE firms_events.event_id = closest.event_id
    AND closest.dist IS NOT NULL;
    """
    
    try:
        result = db.execute(text(sql))
        db.commit()
        print(f"Successfully calculated distances for {result.rowcount} FIRMS events.")
        return result.rowcount
    except Exception as e:
        print(f"Error calculating distances: {e}")
        db.rollback()
        return 0
