from sqlalchemy import Column, BigInteger, Double, String, DateTime
from sqlalchemy.sql import func
from geoalchemy2 import Geography
from app.models.database import Base

class FirmsEvent(Base):
    __tablename__ = "firms_events"

    event_id = Column(BigInteger, primary_key=True, index=True)
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)
    geom = Column(Geography(geometry_type='POINT', srid=4326, spatial_index=True), nullable=False)
    acquisition_time = Column(DateTime, nullable=False, index=True)
    satellite = Column(String(50), index=True)
    instrument = Column(String(50))
    frp = Column(Double)
    confidence = Column(String(10))
    brightness = Column(Double)
    scan = Column(Double)
    track = Column(Double)
    day_night = Column(String(10))
    
    # Enrichment features (Checkpoint 2)
    distance_to_industrial = Column(Double, nullable=True) # Distance in meters
    land_cover_class = Column(String(50), nullable=True) # Textual representation of land cover
    
    created_at = Column(DateTime, default=func.now())

class FirmsHistoricalEvent(Base):
    __tablename__ = "firms_historical"

    event_id = Column(BigInteger, primary_key=True, index=True)
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)
    geom = Column(Geography(geometry_type='POINT', srid=4326, spatial_index=True), nullable=False)
    acquisition_time = Column(DateTime, nullable=False, index=True)
    frp = Column(Double)
