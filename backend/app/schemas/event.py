from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class FirmsEventBase(BaseModel):
    latitude: float
    longitude: float
    acquisition_time: datetime
    satellite: Optional[str] = None
    instrument: Optional[str] = None
    frp: Optional[float] = None
    confidence: Optional[str] = None
    brightness: Optional[float] = None
    scan: Optional[float] = None
    track: Optional[float] = None
    day_night: Optional[str] = None
    
    distance_to_industrial: Optional[float] = None
    land_cover_class: Optional[str] = None

class FirmsEventCreate(FirmsEventBase):
    pass

class FirmsEvent(FirmsEventBase):
    event_id: int
    created_at: datetime

    class Config:
        from_attributes = True
