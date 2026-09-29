from sqlalchemy import Column, BigInteger, Integer, Float, Boolean, ForeignKey, String, Text
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
    # 0 = Natural, 1 = Agricultural, 2 = Persistent Industrial, 3 = Abnormal Industrial
    ml_class = Column(Integer, default=0)
    ml_confidence = Column(Float, default=0.0)

    # Phase 2: Sensor type stored for feature tracking
    sensor_type = Column(String(20), nullable=True)

    # Phase 6: SHAP TreeExplainer attribution (JSON string)
    shap_json = Column(Text, nullable=True)


class FusedEventScore(Base):
    """
    Phase 5b: Fused thermal + atmospheric confidence score per event.
    Stored separately so it can be queried independently of EventFeature.
    """
    __tablename__ = "fused_event_scores"

    event_id          = Column(BigInteger, ForeignKey("firms_events.event_id"), primary_key=True)
    complex_id        = Column(BigInteger, nullable=True)
    fused_score       = Column(Float, default=0.0)
    signal_agreement  = Column(String(30))   # BOTH / THERMAL_ONLY / ATMOSPHERIC_ONLY / NEITHER
    alert_category    = Column(String(200), nullable=True)
    explanation       = Column(Text, nullable=True)
    atmos_max_z       = Column(Float, nullable=True)
    computed_at       = Column(String(25), nullable=True)  # ISO datetime
