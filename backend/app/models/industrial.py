from sqlalchemy import Column, BigInteger, String, Text, DateTime
from sqlalchemy.sql import func
from geoalchemy2 import Geometry, Geography
from app.models.database import Base

class IndustrialSite(Base):
    __tablename__ = "industrial_sites"

    site_id = Column(BigInteger, primary_key=True, index=True)
    osm_id = Column(String(100), unique=True, index=True)
    name = Column(Text)
    facility_type = Column(String(100), index=True)
    source = Column(String(50))
    # We store the polygon as Geometry for OSM rendering, but use centroid Geography for distance math
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=4326, spatial_index=True))
    centroid = Column(Geography(geometry_type='POINT', srid=4326, spatial_index=True))
    created_at = Column(DateTime, default=func.now())
