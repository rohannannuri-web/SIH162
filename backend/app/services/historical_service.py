import random
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.industrial import IndustrialSite
from app.models.firms import FirmsEvent
from app.models.features import IndustrialBaseline, EventFeature

def generate_historical_baselines(db: Session):
    """
    Calculates genuine historical baselines for industrial sites by querying 
    the 1-year historical dataset (firms_historical) to find spatial intersections.
    """
    print("Generating genuine historical baselines from FIRMS historical archive...")
    sites = db.query(IndustrialSite).all()
    
    baselines_added = 0
    for site in sites:
        # Check if already exists
        if db.query(IndustrialBaseline).filter(IndustrialBaseline.site_id == site.site_id).first():
            continue
            
        # Perform spatial join to find all historical events within 2000 meters of the industrial polygon
        sql = text("""
            SELECT 
                COUNT(*),
                COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY frp), 0.0) as median_frp,
                COALESCE(AVG(frp), 0.0) as mean_frp,
                COALESCE(MAX(frp), 0.0) as max_frp
            FROM firms_historical fh
            WHERE ST_DWithin(fh.geom, ST_GeomFromText(:geom, 4326)::geography, 2000)
        """)
        
        # We need the WKT string for the site polygon. For a geometry column, we can do ST_AsText
        # But wait, site.geometry is a WKBElement in SQLAlchemy.
        # Let's run a query to get the WKT directly or compute distance via SQL entirely.
        
        agg_sql = text("""
            SELECT 
                COUNT(fh.event_id) as event_count,
                COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fh.frp), 0.0) as median_frp,
                COALESCE(AVG(fh.frp), 0.0) as mean_frp,
                COALESCE(MAX(fh.frp), 0.0) as max_frp
            FROM firms_historical fh
            WHERE ST_DWithin(fh.geom, (SELECT geometry::geography FROM industrial_sites WHERE site_id = :sid), 2000)
        """)
        
        res = db.execute(agg_sql, {"sid": site.site_id}).fetchone()
        
        count = res[0]
        median_frp = res[1]
        mean_frp = res[2]
        max_frp = res[3]
        
        # Approximate MAD (Median Absolute Deviation) in SQL is tricky, so if count > 0, we can compute it in python
        # or use a rough proxy if we don't fetch all rows. Let's fetch all FRPs to calculate MAD precisely if count > 0.
        mad_frp = 0.0
        if count > 0:
            frp_rows = db.execute(text("""
                SELECT fh.frp 
                FROM firms_historical fh
                WHERE ST_DWithin(fh.geom, (SELECT geometry::geography FROM industrial_sites WHERE site_id = :sid), 2000)
            """), {"sid": site.site_id}).fetchall()
            
            import numpy as np
            frps = np.array([row[0] for row in frp_rows])
            mad_frp = float(np.median(np.abs(frps - median_frp)))
            
        baseline = IndustrialBaseline(
            site_id=site.site_id,
            historical_event_count=count,
            events_per_month=count / 12.0,
            mean_frp=mean_frp,
            median_frp=median_frp,
            max_frp=max_frp,
            frp_mad=mad_frp,
            typical_spatial_spread_m=0.0
        )
        db.add(baseline)
        baselines_added += 1
        
    db.commit()
    print(f"Generated {baselines_added} true industrial baselines.")

def calculate_event_features(db: Session):
    """
    Calculates the final feature vector (EventFeature) for each FIRMS event using 
    its distance to industry, land cover, and the historical baseline of the closest industry.
    """
    print("Calculating final event features for ML classification...")
    events = db.query(FirmsEvent).all()
    
    features_added = 0
    for event in events:
        if db.query(EventFeature).filter(EventFeature.event_id == event.event_id).first():
            continue
            
        # We find the closest industrial site to this event (if any within 5km)
        closest_site_id = None
        if event.distance_to_industrial is not None and event.distance_to_industrial < 5000:
            # Re-query the closest site 
            # (We could store closest_site_id in FirmsEvent during distance calc, but for now we look it up)
            closest_sql = f"""
                SELECT site_id 
                FROM industrial_sites 
                ORDER BY geometry::geography <-> ST_GeomFromText('POINT({event.longitude} {event.latitude})', 4326)::geography 
                LIMIT 1
            """
            result = db.execute(text(closest_sql)).fetchone()
            if result:
                closest_site_id = result[0]
                
        # Get the baseline
        baseline = None
        if closest_site_id:
            baseline = db.query(IndustrialBaseline).filter(IndustrialBaseline.site_id == closest_site_id).first()
            
        # Calculate robust z-score for FRP
        robust_z = 0.0
        ratio = 0.0
        historical_median = 0.0
        historical_count = 0
        
        if baseline and baseline.historical_event_count > 0:
            historical_median = baseline.median_frp
            historical_count = baseline.historical_event_count
            if baseline.median_frp > 0:
                ratio = event.frp / baseline.median_frp
            if baseline.frp_mad > 0:
                robust_z = (event.frp - baseline.median_frp) / (1.4826 * baseline.frp_mad + 0.1) # epsilon
                
        # Populate EventFeature
        feature = EventFeature(
            event_id=event.event_id,
            distance_to_industry_m=event.distance_to_industrial,
            dominant_landcover=event.land_cover_class,
            historical_event_count=historical_count,
            median_historical_frp=historical_median,
            frp_ratio_to_baseline=ratio,
            robust_frp_z=robust_z
        )
        db.add(feature)
        features_added += 1
        
    db.commit()
    print(f"Generated features for {features_added} events.")

