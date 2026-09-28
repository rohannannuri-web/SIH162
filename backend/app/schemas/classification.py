from pydantic import BaseModel
from typing import Optional

class EventFeatureSchema(BaseModel):
    event_id: int
    distance_to_industry_m: Optional[float] = None
    forest_fraction: Optional[float] = None
    cropland_fraction: Optional[float] = None
    grassland_fraction: Optional[float] = None
    builtup_fraction: Optional[float] = None
    bare_fraction: Optional[float] = None
    water_fraction: Optional[float] = None
    dominant_landcover: Optional[str] = None
    
    historical_event_count: Optional[int] = 0
    median_historical_frp: Optional[float] = 0.0
    frp_ratio_to_baseline: Optional[float] = 0.0
    robust_frp_z: Optional[float] = 0.0
    
    ml_class: Optional[int] = 0

    class Config:
        from_attributes = True
