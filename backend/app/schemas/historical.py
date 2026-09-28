from pydantic import BaseModel
from typing import Optional

class IndustrialBaselineSchema(BaseModel):
    site_id: int
    historical_event_count: Optional[int] = 0
    events_per_month: Optional[float] = 0.0
    mean_frp: Optional[float] = 0.0
    median_frp: Optional[float] = 0.0
    max_frp: Optional[float] = 0.0
    frp_mad: Optional[float] = 0.0
    typical_spatial_spread_m: Optional[float] = 0.0

    class Config:
        from_attributes = True
