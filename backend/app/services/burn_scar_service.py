"""
burn_scar_service.py — Phase 5b + 5c: Optical burn confirmation + SAR fallback
================================================================================
Phase 5b: Sentinel-2 L2A delta-NBR (Normalized Burn Ratio difference)
  NBR      = (B8_NIR - B12_SWIR) / (B8_NIR + B12_SWIR)
  delta_NBR = pre_event_NBR - post_event_NBR
  Threshold: delta_NBR >= 0.27 → CONFIRMED burn/ground disturbance
  
  Literature basis for 0.27 threshold:
    Key, C.H. & Benson, N.C. (2006). Landscape Assessment: Ground measure of
    severity, the Composite Burn Index; and Remote sensing of severity, the
    Normalized Burn Ratio. In: Lutes, D.C. et al. (eds), FIREMON: Fire Effects
    Monitoring and Inventory System. USDA Forest Service Gen. Tech. Rep.
    RMRS-GTR-164-CD: LA-1-51.
    Moderate = 0.10-0.27, High = 0.27-0.65+.  We use 0.27 (high-severity onset)
    as the signal threshold for confirmed industrial-scale burn/disturbance.

Phase 5c: Sentinel-1 SAR RTC change detection (cloud-independent)
  Triggered when Sentinel-2 cloud fraction >= CLOUD_FRACTION_THRESHOLD.
  VV backscatter changes: burned/disturbed soil loses the volume scattering
  component present in intact vegetation → VV decreases post-fire.
  Threshold: |post_mean - pre_mean| / |pre_mean| >= SAR_CHANGE_THRESHOLD.
  
Coverage reporting:
  Each analysis records which channel was used ('S2', 'S1', 'none').
  Downstream fusion scoring aggregates these to report the fraction of events
  confirmed optically vs SAR-only vs unconfirmable. This quantifies the real
  value of adding 5c.

Data source: Both Sentinel-2 L2A and Sentinel-1 RTC are freely available on
  Microsoft Planetary Computer STAC (same access pattern as WorldCover and S5P).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import planetary_computer
from pystac_client import Client
from sqlalchemy.orm import Session

from app.models.database import Base
from sqlalchemy import Column, BigInteger, Float, String, Boolean, DateTime, Integer
from sqlalchemy.sql import func

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
DELTA_NBR_BURN_THRESHOLD = 0.27   # High-severity burn onset (Key & Benson 2006)
CLOUD_FRACTION_THRESHOLD = 0.30   # >30% cloud cover → use SAR instead
SAR_CHANGE_THRESHOLD = 0.15       # 15% relative VV backscatter change → disturbance
PRE_EVENT_WINDOW_DAYS = 30        # Search this many days BEFORE event for pre-scene
POST_EVENT_WINDOW_DAYS = 30       # Search this many days AFTER event for post-scene
MIN_POST_EVENT_DAYS = 2           # Need at least 2 days for a meaningful post-scene

PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# ─────────────────────────────────────────────────────────────────────────────
# DB Model
# ─────────────────────────────────────────────────────────────────────────────
class BurnScarResult(Base):
    """
    Per-event burn/ground-disturbance confirmation result.
    One row per (event_id) — updated in place if re-analyzed.
    """
    __tablename__ = "burn_scar_results"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id        = Column(BigInteger, nullable=False, index=True)
    complex_id      = Column(BigInteger, nullable=True, index=True)

    # Which channel produced the result
    channel_used    = Column(String(10))   # 'S2', 'S1', 'none', 'pending'

    # Sentinel-2 result
    delta_nbr            = Column(Float, nullable=True)
    cloud_fraction_pct   = Column(Float, nullable=True)
    is_burn_confirmed_s2 = Column(Boolean, default=False)

    # Sentinel-1 SAR result
    sar_change_fraction  = Column(Float, nullable=True)
    is_burn_confirmed_s1 = Column(Boolean, default=False)

    # Consolidated result
    is_confirmed    = Column(Boolean, default=False)
    pre_event_date  = Column(String(10), nullable=True)
    post_event_date = Column(String(10), nullable=True)
    reason          = Column(String(200), nullable=True)   # Explains 'none'
    computed_at     = Column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _open_pc_client():
    return Client.open(PC_STAC_URL, modifier=planetary_computer.sign_inplace)


def _search_s2_scene(client, lon: float, lat: float, date_from: str, date_to: str) -> Optional[object]:
    """Find the least-cloudy Sentinel-2 L2A scene in a date window."""
    try:
        search = client.search(
            collections=["sentinel-2-l2a"],
            intersects={"type": "Point", "coordinates": [lon, lat]},
            datetime=f"{date_from}/{date_to}",
            query={"eo:cloud_cover": {"lt": 95}},
            sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
            max_items=5,
        )
        items = list(search.items())
        return items[0] if items else None
    except Exception:
        return None


def _compute_nbr_from_scene(item, lon: float, lat: float) -> Optional[tuple[float, float]]:
    """
    Sample B8 (NIR) and B12 (SWIR) from a Sentinel-2 scene at (lon, lat).
    Returns (nbr, cloud_fraction) or None if data unavailable.
    """
    try:
        import rasterio
        from pyproj import Transformer

        # Cloud fraction from scene metadata
        cloud_pct = float(item.properties.get("eo:cloud_cover", 50.0)) / 100.0

        # NIR (B8) and SWIR (B12) band assets
        b8_href  = item.assets.get("B08") or item.assets.get("nir")
        b12_href = item.assets.get("B12") or item.assets.get("swir22")

        if b8_href is None or b12_href is None:
            return None

        def _sample_band(href_asset, lon, lat):
            href = href_asset.href
            with rasterio.open(href) as src:
                transformer = Transformer.from_crs("epsg:4326", src.crs, always_xy=True)
                x, y = transformer.transform(lon, lat)
                val = list(src.sample([(x, y)]))[0][0]
                # Sentinel-2 L2A reflectance is scaled by 10000
                return float(val) / 10000.0 if val is not None else None

        nir  = _sample_band(b8_href, lon, lat)
        swir = _sample_band(b12_href, lon, lat)

        if nir is None or swir is None or (nir + swir) == 0:
            return None

        nbr = (nir - swir) / (nir + swir)
        return nbr, cloud_pct

    except Exception:
        return None


def _search_s1_scene(client, lon: float, lat: float, date_from: str, date_to: str) -> Optional[object]:
    """Find Sentinel-1 RTC scene in date window."""
    try:
        search = client.search(
            collections=["sentinel-1-rtc"],
            intersects={"type": "Point", "coordinates": [lon, lat]},
            datetime=f"{date_from}/{date_to}",
            max_items=3,
        )
        items = list(search.items())
        return items[0] if items else None
    except Exception:
        return None


def _sample_sar_vv(item, lon: float, lat: float) -> Optional[float]:
    """Sample VV polarization backscatter from a Sentinel-1 RTC scene."""
    try:
        import rasterio
        from pyproj import Transformer

        vv_asset = item.assets.get("vv") or item.assets.get("VV")
        if vv_asset is None:
            return None

        with rasterio.open(vv_asset.href) as src:
            transformer = Transformer.from_crs("epsg:4326", src.crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
            val = list(src.sample([(x, y)]))[0][0]
            return float(val) if val is not None and val > -9999 else None

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def analyze_burn_scar(
    db: Session,
    event_id: int,
    lon: float,
    lat: float,
    event_date_str: str,   # YYYY-MM-DD
    complex_id: Optional[int] = None,
) -> dict:
    """
    Attempt to confirm burn/ground disturbance for a thermal event via:
      1. Sentinel-2 ΔNBR (optical) if cloud fraction < CLOUD_FRACTION_THRESHOLD
      2. Sentinel-1 SAR change (all-weather) if cloud fraction >= threshold

    Result is persisted to burn_scar_results and returned as a dict.

    Returns:
    {
        "event_id": int,
        "channel_used": "S2" | "S1" | "none",
        "is_confirmed": bool,
        "delta_nbr": float | None,
        "cloud_fraction_pct": float | None,
        "sar_change_fraction": float | None,
        "pre_event_date": str | None,
        "post_event_date": str | None,
        "reason": str,
    }
    """
    # Check for existing result
    existing = db.query(BurnScarResult).filter(
        BurnScarResult.event_id == event_id
    ).first()
    if existing:
        return _result_to_dict(existing)

    event_dt = datetime.strptime(event_date_str, "%Y-%m-%d")
    result_obj = BurnScarResult(
        event_id=event_id,
        complex_id=complex_id,
        channel_used="none",
        is_confirmed=False,
        reason="Analysis pending",
    )
    db.add(result_obj)
    db.flush()

    # Check if post-event scene is even possible yet
    days_since_event = (datetime.utcnow() - event_dt).days
    if days_since_event < MIN_POST_EVENT_DAYS:
        result_obj.reason = f"Event too recent ({days_since_event}d ago) — post-event scene not yet available."
        db.commit()
        return _result_to_dict(result_obj)

    pre_from  = (event_dt - timedelta(days=PRE_EVENT_WINDOW_DAYS)).strftime("%Y-%m-%d")
    pre_to    = (event_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    post_from = (event_dt + timedelta(days=MIN_POST_EVENT_DAYS)).strftime("%Y-%m-%d")
    post_to   = (event_dt + timedelta(days=POST_EVENT_WINDOW_DAYS)).strftime("%Y-%m-%d")

    client = _open_pc_client()

    # ── Attempt Sentinel-2 ΔNBR ────────────────────────────────────────────
    pre_item  = _search_s2_scene(client, lon, lat, pre_from, pre_to)
    post_item = _search_s2_scene(client, lon, lat, post_from, post_to)

    if pre_item and post_item:
        pre_result  = _compute_nbr_from_scene(pre_item, lon, lat)
        post_result = _compute_nbr_from_scene(post_item, lon, lat)

        if pre_result and post_result:
            pre_nbr,  pre_cloud  = pre_result
            post_nbr, post_cloud = post_result
            max_cloud = max(pre_cloud, post_cloud)
            delta_nbr = pre_nbr - post_nbr

            result_obj.delta_nbr          = round(delta_nbr, 4)
            result_obj.cloud_fraction_pct = round(max_cloud * 100, 1)
            result_obj.pre_event_date     = pre_item.datetime.strftime("%Y-%m-%d")
            result_obj.post_event_date    = post_item.datetime.strftime("%Y-%m-%d")

            if max_cloud < CLOUD_FRACTION_THRESHOLD:
                # Cloud-free enough → use optical result
                result_obj.channel_used = "S2"
                result_obj.is_burn_confirmed_s2 = delta_nbr >= DELTA_NBR_BURN_THRESHOLD
                result_obj.is_confirmed = result_obj.is_burn_confirmed_s2
                result_obj.reason = (
                    f"Optical confirmed: delta_NBR={delta_nbr:.3f} "
                    f"({'>='+str(DELTA_NBR_BURN_THRESHOLD)+'=BURN' if result_obj.is_confirmed else 'below threshold'}) "
                    f"Cloud={max_cloud*100:.0f}%"
                )
                db.commit()
                return _result_to_dict(result_obj)
            else:
                # Cloud-covered → fallthrough to SAR
                result_obj.reason = f"Cloud cover {max_cloud*100:.0f}% > {CLOUD_FRACTION_THRESHOLD*100:.0f}% threshold — using SAR"

    # ── Fallback: Sentinel-1 SAR ────────────────────────────────────────────
    s1_pre  = _search_s1_scene(client, lon, lat, pre_from, pre_to)
    s1_post = _search_s1_scene(client, lon, lat, post_from, post_to)

    if s1_pre and s1_post:
        vv_pre  = _sample_sar_vv(s1_pre, lon, lat)
        vv_post = _sample_sar_vv(s1_post, lon, lat)

        if vv_pre is not None and vv_post is not None and abs(vv_pre) > 1e-10:
            change = abs(vv_post - vv_pre) / abs(vv_pre)
            result_obj.sar_change_fraction = round(change, 4)
            result_obj.channel_used = "S1"
            result_obj.is_burn_confirmed_s1 = change >= SAR_CHANGE_THRESHOLD
            result_obj.is_confirmed = result_obj.is_burn_confirmed_s1
            result_obj.pre_event_date  = s1_pre.datetime.strftime("%Y-%m-%d")
            result_obj.post_event_date = s1_post.datetime.strftime("%Y-%m-%d")
            result_obj.reason = (
                f"SAR change={change*100:.1f}% "
                f"({'DISTURBANCE CONFIRMED' if result_obj.is_confirmed else 'below threshold'}) "
                f"(threshold={SAR_CHANGE_THRESHOLD*100:.0f}%)"
            )
            db.commit()
            return _result_to_dict(result_obj)

    # ── No usable scene found ───────────────────────────────────────────────
    result_obj.channel_used = "none"
    result_obj.reason = "No usable Sentinel-2 or Sentinel-1 scene found in search windows."
    db.commit()
    return _result_to_dict(result_obj)


def _result_to_dict(r: BurnScarResult) -> dict:
    return {
        "event_id": r.event_id,
        "channel_used": r.channel_used,
        "is_confirmed": r.is_confirmed,
        "delta_nbr": r.delta_nbr,
        "cloud_fraction_pct": r.cloud_fraction_pct,
        "sar_change_fraction": r.sar_change_fraction,
        "is_burn_confirmed_s2": r.is_burn_confirmed_s2,
        "is_burn_confirmed_s1": r.is_burn_confirmed_s1,
        "pre_event_date": r.pre_event_date,
        "post_event_date": r.post_event_date,
        "reason": r.reason,
    }


def get_burn_coverage_stats(db: Session) -> dict:
    """
    Report the fraction of events confirmed via S2 vs S1 vs neither.
    This quantifies the real value of adding SAR (Phase 5c).
    Called at end of atmospheric pipeline phase and stored in logs.
    """
    total    = db.query(BurnScarResult).count()
    s2_used  = db.query(BurnScarResult).filter(BurnScarResult.channel_used == "S2").count()
    s1_used  = db.query(BurnScarResult).filter(BurnScarResult.channel_used == "S1").count()
    none_    = db.query(BurnScarResult).filter(BurnScarResult.channel_used == "none").count()
    confirmed = db.query(BurnScarResult).filter(BurnScarResult.is_confirmed == True).count()

    if total == 0:
        return {"total": 0, "message": "No burn scar analyses run yet."}

    return {
        "total_analyzed": total,
        "s2_optical_used_pct": round(100 * s2_used / total, 1),
        "s1_sar_fallback_pct": round(100 * s1_used / total, 1),
        "no_scene_pct": round(100 * none_ / total, 1),
        "confirmed_burn_pct": round(100 * confirmed / total, 1),
        "note": (
            "s1_sar_fallback_pct quantifies the real coverage gain from adding SAR. "
            "Events in this bucket would have returned null without Sentinel-1."
        ),
    }
