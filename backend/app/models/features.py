from sqlalchemy import Column, BigInteger, Integer, Float, Boolean, ForeignKey, String
from app.models.database import Base

class IndustrialBaseline(Base):
    __tablename__ = "industrial_baselines"

    site_id = Column(BigInteger, ForeignKey("industrial_sites.site_id"), primary_key=True)
    historical_event_count = Column(Integer, default=0)
    events_per_month = Column(Float, default=0.0)
    mean_frp = Column(Float, default=0.0)
    median_frp = Column(Float, default=0.0)
    max_frp = Column(Float, default=0.0)
    frp_mad = Column(Float, default=0.0) # Median Absolute Deviation
    typical_spatial_spread_m = Column(Float, default=0.0) # Radius containing 90% of events

class EventFeature(Base):
    __tablename__ = "event_features"

    event_id = Column(BigInteger, ForeignKey("firms_events.event_id"), primary_key=True)
    
    # Spatial Features
    distance_to_industry_m = Column(Float)
    
    # Land Cover Features
    forest_fraction = Column(Float, default=0.0)
    cropland_fraction = Column(Float, default=0.0)
    grassland_fraction = Column(Float, default=0.0)
    builtup_fraction = Column(Float, default=0.0)
    bare_fraction = Column(Float, default=0.0)
    water_fraction = Column(Float, default=0.0)
    dominant_landcover = Column(String(100))
    
    # Temporal / Historical Features
    historical_event_count = Column(Integer, default=0)
    median_historical_frp = Column(Float, default=0.0)
    frp_ratio_to_baseline = Column(Float, default=0.0)
    robust_frp_z = Column(Float, default=0.0)
    
    # Target / Label (for ML)
    # 0 = Unknown, 1 = Natural, 2 = Agricultural, 3 = Normal Industrial, 4 = Abnormal Industrial
    ml_class = Column(Integer, default=0) 
    ml_confidence = Column(Float, default=0.0)
