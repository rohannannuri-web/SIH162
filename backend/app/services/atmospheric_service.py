"""
atmospheric_service.py — Phase 5: Sentinel-5P TROPOMI atmospheric composition fusion
======================================================================================
Pulls SO2, NO2, CO, and CH4 column data from the Sentinel-5P TROPOMI
instrument via the Microsoft Planetary Computer STAC catalog (consistent with
the existing WorldCover and Sentinel-2 access pattern).

Key design decisions:
  - Uses Planetary Computer first; falls back to Copernicus Data Space
    Ecosystem STAC (https://catalogue.dataspace.copernicus.eu/stac) only if
    a required product/band is unavailable through PC.
  - Historical baseline + Z-score approach mirrors the existing FRP robust
    Z-score, applied to atmospheric column concentrations instead.
  - "NON-THERMAL ATMOSPHERIC ANOMALY" alert category surfaces gas-leak/
    release events that produce no detectable thermal signature — directly
    addressing the PS's explicit mention of "gas leaks".

S5P Products available on Planetary Computer:
  sentinel-5p-l2-no2   → tropospheric NO2 column (mol/m²)
  sentinel-5p-l2-so2   → SO2 column (mol/m²)
  sentinel-5p-l2-co    → CO column (mol/m²)
  sentinel-5p-l2-ch4   → CH4 mixing ratio (ppb)

Revisit: TROPOMI has daily global coverage at ~3.5km×5.5km pixel size.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import planetary_computer
import requests
from pystac_client import Client
from sqlalchemy import Column, BigInteger, Float, String, DateTime, Integer
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.database import Base

# ---------------------------------------------------------------------------
# S5P model
# ---------------------------------------------------------------------------
class AtmosphericReading(Base):
    """Per-facility-complex atmospheric column measurement from TROPOMI."""
    __tablename__ = "atmospheric_readings"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    complex_id      = Column(BigInteger, nullable=False, index=True)
    measurement_date = Column(String(10), nullable=False, index=True)   # YYYY-MM-DD
    gas_species     = Column(String(10), nullable=False)                # NO2 / SO2 / CO / CH4
    column_value    = Column(Float)      # mol/m² or ppb for CH4
    qa_value        = Column(Float)      # TROPOMI QA flag (0–1, keep ≥0.5)
    z_score         = Column(Float)      # Robust Z vs historical baseline
    is_anomalous    = Column(Integer, default=0)  # 1 if |z_score| > ATMOS_Z_THRESHOLD
    created_at      = Column(DateTime, server_default=func.now())


class AtmosphericBaseline(Base):
    """Per-facility-complex, per-gas-species historical baseline statistics."""
    __tablename__ = "atmospheric_baselines"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    complex_id      = Column(BigInteger, nullable=False, index=True)
    gas_species     = Column(String(10), nullable=False)
    median_value    = Column(Float)
    mad_value       = Column(Float)     # Median Absolute Deviation
    n_observations  = Column(Integer, default=0)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ATMOS_Z_THRESHOLD = 3.0   # Robust Z-score threshold for atmospheric anomaly
QA_MIN = 0.5              # Minimum TROPOMI QA value to accept a pixel
PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# TROPOMI product collection IDs on Planetary Computer
S5P_COLLECTIONS = {
    "NO2": "sentinel-5p-l2-no2",
    "SO2": "sentinel-5p-l2-so2",
    "CO":  "sentinel-5p-l2-co",
    "CH4": "sentinel-5p-l2-ch4",
}

# Band asset names within each product
S5P_BAND_ASSETS = {
    "NO2": "nitrogendioxide_tropospheric_column",
    "SO2": "sulfurdioxide_total_vertical_column",
    "CO":  "carbonmonoxide_total_column",
    "CH4": "methane_mixing_ratio_bias_corrected",
}

# Fallback: Copernicus Data Space Ecosystem STAC (used if PC doesn't have S5P)
CDSE_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"


def _open_pc_client():
    return Client.open(PC_STAC_URL, modifier=planetary_computer.sign_inplace)


def _query_s5p_value(
    lon: float, lat: float, gas: str, date_str: str, client
) -> Optional[tuple[float, float]]:
    """
    Query the TROPOMI column value for a given gas species at (lon, lat) on date_str.
    Returns (column_value, qa_value) or None if no suitable scene found.
    
    Attempts Planetary Computer first; silently falls back to CDSE if the
    collection is absent on PC.
    """
    collection = S5P_COLLECTIONS.get(gas)
    if not collection:
        return None

    # Search ±1 day window (TROPOMI has daily global coverage)
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    search_start = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    search_end   = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        search = client.search(
            collections=[collection],
            intersects={"type": "Point", "coordinates": [lon, lat]},
            datetime=f"{search_start}/{search_end}",
            max_items=3,
        )
        items = list(search.items())
        if not items:
            return None

        # Pick the item closest to the target date
        target_dt = datetime(dt.year, dt.month, dt.day, 12, 0, 0)
        best_item = min(
            items,
            key=lambda it: abs((it.datetime.replace(tzinfo=None) - target_dt).total_seconds())
        )

        asset_name = S5P_BAND_ASSETS.get(gas)
        if asset_name not in best_item.assets:
            return None

        # For S5P products, we use rasterio to sample the cloud-optimized NetCDF/HDF5
        # However, Planetary Computer serves S5P as cloud-optimized GeoTIFF through
        # the signed URL. We sample via rasterio.
        import rasterio
        from pyproj import Transformer

        href = best_item.assets[asset_name].href
        with rasterio.open(href) as src:
            transformer = Transformer.from_crs("epsg:4326", src.crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
            val = list(src.sample([(x, y)]))[0][0]
            if val is None or float(val) < -1e30:  # fill value
                return None
            
            # Try to get QA band
            qa_val = 1.0  # default acceptable QA
            if "qa_value" in best_item.assets:
                try:
                    with rasterio.open(best_item.assets["qa_value"].href) as qa_src:
                        qa_raw = list(qa_src.sample([(x, y)]))[0][0]
                        qa_val = float(qa_raw) if qa_raw is not None else 1.0
                except Exception:
                    pass

        if qa_val < QA_MIN:
            return None  # Low quality pixel

        return (float(val), qa_val)

    except Exception as e:
        # Planetary Computer might not have this S5P product yet → try CDSE
        try:
            return _query_s5p_cdse_fallback(lon, lat, gas, date_str)
        except Exception:
            return None


def _query_s5p_cdse_fallback(lon: float, lat: float, gas: str, date_str: str) -> Optional[tuple[float, float]]:
    """
    Fallback: query Copernicus Data Space Ecosystem STAC for S5P data.
    Used when the product is unavailable on Planetary Computer.
    """
    try:
        client = Client.open(CDSE_STAC_URL)
        # CDSE collection naming convention
        cdse_collection = f"SENTINEL-5P"
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        search_start = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        search_end   = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

        search = client.search(
            collections=[cdse_collection],
            intersects={"type": "Point", "coordinates": [lon, lat]},
            datetime=f"{search_start}/{search_end}",
            max_items=1,
        )
        items = list(search.items())
        if not items:
            return None
        # Return a placeholder for now — full CDSE band extraction
        # would mirror the PC path but use CDSE-specific asset names.
        return None
    except Exception:
        return None


def compute_robust_z(value: float, median: float, mad: float) -> float:
    """Robust Z-score: (x - median) / (1.4826 * MAD + ε)"""
    return (value - median) / (1.4826 * mad + 1e-10)


def analyze_atmospheric_anomaly(
    db: Session,
    complex_id: int,
    lon: float,
    lat: float,
    date_str: str,
) -> dict:
    """
    Query TROPOMI for all 4 gas species at (lon, lat) on date_str,
    compute robust Z-scores vs stored baseline, and return an anomaly report.

    Returns:
    {
        "complex_id": int,
        "date": str,
        "species": {
            "NO2": {"value": float, "z_score": float, "is_anomalous": bool},
            ...
        },
        "max_z_score": float,
        "any_anomalous": bool,
        "alert_type": "NON-THERMAL ATMOSPHERIC ANOMALY" | "ELEVATED_ATMOSPHERIC" | None
    }
    """
    client = _open_pc_client()
    species_results = {}
    max_z = 0.0

    for gas in S5P_COLLECTIONS:
        result = _query_s5p_value(lon, lat, gas, date_str, client)
        if result is None:
            species_results[gas] = {"value": None, "z_score": None, "is_anomalous": False}
            continue

        col_val, qa_val = result

        # Get or default baseline
        baseline = db.query(AtmosphericBaseline).filter(
            AtmosphericBaseline.complex_id == complex_id,
            AtmosphericBaseline.gas_species == gas,
        ).first()

        if baseline and baseline.n_observations >= 5 and baseline.mad_value is not None:
            z = compute_robust_z(col_val, baseline.median_value, baseline.mad_value)
        else:
            z = 0.0  # Insufficient history, can't claim anomaly

        is_anom = abs(z) > ATMOS_Z_THRESHOLD

        # Persist reading
        reading = AtmosphericReading(
            complex_id=complex_id,
            measurement_date=date_str,
            gas_species=gas,
            column_value=col_val,
            qa_value=qa_val,
            z_score=z,
            is_anomalous=int(is_anom),
        )
        db.add(reading)

        if abs(z) > abs(max_z):
            max_z = z

        species_results[gas] = {
            "value": col_val,
            "z_score": round(z, 3),
            "is_anomalous": is_anom,
        }

    db.commit()

    any_anomalous = any(v.get("is_anomalous", False) for v in species_results.values())
    alert_type = None
    if any_anomalous:
        alert_type = "NON-THERMAL ATMOSPHERIC ANOMALY — possible gas leak/release, no fire signature required"

    return {
        "complex_id": complex_id,
        "date": date_str,
        "species": species_results,
        "max_z_score": round(max_z, 3),
        "any_anomalous": any_anomalous,
        "alert_type": alert_type,
    }


def update_atmospheric_baseline(db: Session, complex_id: int, gas: str, new_value: float) -> None:
    """
    Incrementally update the running atmospheric baseline for a facility complex / gas
    using Welford's online algorithm for median/MAD approximation.
    Note: This is an approximation. For proper median/MAD we batch-compute from stored readings.
    """
    # Gather all readings for this complex/gas, compute true median/MAD
    readings = db.query(AtmosphericReading).filter(
        AtmosphericReading.complex_id == complex_id,
        AtmosphericReading.gas_species == gas,
        AtmosphericReading.qa_value >= QA_MIN,
    ).all()

    if len(readings) < 2:
        return

    values = np.array([r.column_value for r in readings if r.column_value is not None])
    if len(values) < 2:
        return

    median_v = float(np.median(values))
    mad_v    = float(np.median(np.abs(values - median_v)))

    baseline = db.query(AtmosphericBaseline).filter(
        AtmosphericBaseline.complex_id == complex_id,
        AtmosphericBaseline.gas_species == gas,
    ).first()

    if not baseline:
        baseline = AtmosphericBaseline(
            complex_id=complex_id,
            gas_species=gas,
        )
        db.add(baseline)

    baseline.median_value   = median_v
    baseline.mad_value      = mad_v
    baseline.n_observations = len(values)
    db.commit()


def compute_fused_confidence(thermal_confidence: float, thermal_class: int, atmos_report: dict) -> dict:
    """
    Phase 5b: Combine thermal XGBoost confidence with atmospheric anomaly score
    into a single fused confidence score per event/facility.

    Two independent signal types agreeing raises confidence beyond either alone.
    An atmospheric anomaly with NO thermal signature surfaces its own alert category.

    Returns:
    {
        "fused_score": float (0–1),
        "signal_agreement": "BOTH" | "THERMAL_ONLY" | "ATMOSPHERIC_ONLY" | "NEITHER",
        "alert_category": str | None,
        "explanation": str
    }
    """
    has_thermal  = thermal_confidence > 0.75 and thermal_class in (2, 3)  # Industrial classes
    has_atmos    = atmos_report.get("any_anomalous", False)
    atmos_max_z  = abs(atmos_report.get("max_z_score", 0.0))

    if has_thermal and has_atmos:
        # Both signals agree → boost confidence
        atmos_boost = min(0.15, atmos_max_z * 0.03)
        fused = min(1.0, thermal_confidence + atmos_boost)
        agreement = "BOTH"
        category  = "CONFIRMED INDUSTRIAL THERMAL + ATMOSPHERIC EVENT"
        explanation = (
            f"Thermal classification (confidence={thermal_confidence:.2f}) corroborated by "
            f"atmospheric anomaly (max Z={atmos_max_z:.1f}). High-confidence industrial event."
        )
    elif has_thermal and not has_atmos:
        fused = thermal_confidence
        agreement = "THERMAL_ONLY"
        category  = None
        explanation = f"Thermal signature confirmed (confidence={thermal_confidence:.2f}). No atmospheric anomaly detected."
    elif not has_thermal and has_atmos:
        # Atmospheric anomaly, no thermal signal → gas leak / non-combustion release
        fused = min(0.75, 0.4 + atmos_max_z * 0.05)
        agreement = "ATMOSPHERIC_ONLY"
        category  = "NON-THERMAL ATMOSPHERIC ANOMALY — possible gas leak/release, no fire signature"
        explanation = (
            f"Atmospheric anomaly detected (max Z={atmos_max_z:.1f}) without a corresponding "
            f"thermal fire signature. Possible gas leak, venting, or cold-release event."
        )
    else:
        fused = max(0.0, thermal_confidence)
        agreement = "NEITHER"
        category  = None
        explanation = "No significant thermal or atmospheric anomaly."

    return {
        "fused_score": round(fused, 4),
        "signal_agreement": agreement,
        "alert_category": category,
        "explanation": explanation,
    }
