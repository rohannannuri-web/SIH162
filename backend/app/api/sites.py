from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.industrial import IndustrialSite
from app.schemas.site import IndustrialSite as IndustrialSiteSchema
from typing import List

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[IndustrialSiteSchema])
def get_all_sites(limit: int = 500, db: Session = Depends(get_db)):
    """Retrieve all industrial sites."""
    sites = db.query(IndustrialSite).limit(limit).all()
    return sites

@router.get("/geojson")
def get_sites_geojson(db: Session = Depends(get_db)):
    """Returns Industrial Sites as a GeoJSON FeatureCollection using their centroids."""
    sites = db.query(IndustrialSite).all()
    features = []
    for site in sites:
        # Since we just need the centroid for the map point, we can extract from SQL
        # or use GeoAlchemy scalar methods. For simplicity and speed, we will query the WKT.
        # But wait, we can just do a query for ST_X and ST_Y.
        point = db.scalar(site.centroid.ST_AsText()) if site.centroid else None
        
        # A rough parsing of POINT(lon lat)
        lon, lat = 0.0, 0.0
        if point and point.startswith("POINT"):
            coords = point.replace("POINT(", "").replace(")", "").split(" ")
            if len(coords) == 2:
                lon = float(coords[0])
                lat = float(coords[1])
                
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "site_id": site.site_id,
                "osm_id": site.osm_id,
                "name": site.name,
                "facility_type": site.facility_type,
                "source": site.source
            }
        })
    return {
        "type": "FeatureCollection",
        "features": features
    }

@router.get("/{site_id}", response_model=IndustrialSiteSchema)
def get_site_by_id(site_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific industrial site by ID."""
    site = db.query(IndustrialSite).filter(IndustrialSite.site_id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Industrial site not found")
    return site
