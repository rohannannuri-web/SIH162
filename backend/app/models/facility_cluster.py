"""
facility_cluster.py  — Phase 3a: Facility-complex clustering
=============================================================
Spatially clusters nearby OSM industrial polygons (and the curated seed
layer) into single "facility complex" entities using DBSCAN on centroids.

Why this matters:
  A large, dispersed industrial source (e.g. a sprawling flare field or a
  refinery with multiple process units spread over 3-5km) will never reach a
  per-site recurrence threshold because no single OSM polygon sees enough
  repeated activity on its own. Clustering makes the *complex* the unit of
  persistence keying, not any individual polygon within it.

DBSCAN parameters:
  eps = CLUSTER_RADIUS_KM (default 3km) converted to radians for
  haversine metric; min_samples = 1 (every site is in *some* cluster —
  isolated sites form singleton clusters).
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy import Column, BigInteger, String, Float, Text, Integer
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from geoalchemy2 import Geography

from app.models.database import Base

# ---------------------------------------------------------------------------
# Tunable constant — raise/lower to merge/split facility complexes
# ---------------------------------------------------------------------------
CLUSTER_RADIUS_KM = 3.0     # DBSCAN eps: merge sites within this distance

# ---------------------------------------------------------------------------
# SQLAlchemy model
# ---------------------------------------------------------------------------
class FacilityComplex(Base):
    """
    A spatially-clustered grouping of one or more industrial sites.
    Primary key is the cluster label assigned by DBSCAN.
    The centroid_lat/lon is the geometric mean of constituent site centroids.
    """
    __tablename__ = "facility_complexes"

    complex_id   = Column(BigInteger, primary_key=True, autoincrement=True)
    name         = Column(Text)           # Derived from dominant member name
    facility_type = Column(String(100))   # Most common type among members
    member_count = Column(Integer, default=1)
    centroid_lat = Column(Float)
    centroid_lon = Column(Float)
    centroid_geom = Column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )
    radius_m     = Column(Float)          # Bounding radius of member sites
    source       = Column(String(50))
    created_at   = Column(DateTime, server_default=func.now())


class FacilityHysteresisState(Base):
    """
    Tracks the hysteresis state per facility complex.

    States:
      ROUTINE    — baseline thermal activity, no anomaly
      ABNORMAL   — currently classified as abnormal/accidental
      RECOVERING — consecutive clear windows being counted toward re-baseline

    Once in ABNORMAL, the complex must show HYSTERESIS_CLEAR_DAYS consecutive
    calendar days of non-anomalous detections before transitioning to ROUTINE.
    """
    __tablename__ = "facility_hysteresis"

    complex_id         = Column(BigInteger, primary_key=True)
    state              = Column(String(20), default="ROUTINE")
    # ISO-date string (YYYY-MM-DD) of last detected anomalous window
    last_anomaly_date  = Column(String(20), nullable=True)
    # ISO-date string of last clear detection window (anchor for streak accumulation)
    last_clear_date    = Column(String(20), nullable=True)
    # Number of consecutive clear days accumulated since last anomaly
    clear_days_streak  = Column(Integer, default=0)
    # Running tally of times this complex has entered ABNORMAL state
    total_abnormal_events = Column(Integer, default=0)
