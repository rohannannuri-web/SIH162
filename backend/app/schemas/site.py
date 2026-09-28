from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class IndustrialSiteBase(BaseModel):
    osm_id: str
    name: Optional[str] = None
    facility_type: Optional[str] = None
    source: str = "OSM"

class IndustrialSiteCreate(IndustrialSiteBase):
    pass

class IndustrialSite(IndustrialSiteBase):
    site_id: int
    created_at: datetime

    class Config:
        from_attributes = True
