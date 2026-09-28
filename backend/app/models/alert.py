from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.models.database import Base

class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, index=True)
    event_id = Column(BigInteger, ForeignKey("firms_events.event_id"))
    
    title = Column(String(200))
    facility = Column(String(200))
    classification = Column(String(100))
    confidence = Column(Float)
    risk = Column(String(20))
    
    frp = Column(Float)
    baseline_frp = Column(Float)
    frp_ratio = Column(Float)
    
    latitude = Column(Float)
    longitude = Column(Float)
    
    is_active = Column(Boolean, default=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
