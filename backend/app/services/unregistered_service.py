"""
unregistered_service.py — Phase 6: Unregistered-activity prioritization
=========================================================================
Any high-confidence anomaly (thermal, atmospheric, or nighttime) with no
facility-complex match within 3km is surfaced as an UNREGISTERED_ACTIVITY
priority alert.

This is a deliberate design choice, documented as such:
  The absence of a known facility registration is itself evidence, not a
  reason to suppress the alert. Unregistered industrial activity — illegal
  quarrying, brick kilns operating outside registered zones, unregistered
  gas flares, small-scale smelters — is a real phenomenon in India and is
  explicitly in scope for this problem statement.

False-positive protection (Phase 6 requirement):
  Brick kilns in the Indo-Gangetic Plains fire seasonally October-June.
  Their intermittent pattern MUST NOT be routed into UNREGISTERED_ACTIVITY.
  The gem_service.is_in_brick_kiln_belt() check prevents this.
  
  Similarly, the Jharia coalfield has persistent natural coal-seam fires;
  these are always mapped (source=GEM) and should never trigger unregistered
  alerts.

Alert categories produced:
  - UNREGISTERED_THERMAL    : High-confidence thermal, no facility match
  - SEASONAL_KILN_ACTIVITY  : Brick kiln pattern in kiln belt (not anomalous)
  - COAL_SEAM_FIRE          : In Jharia zone (not anomalous)
  - UNREGISTERED_ATMOSPHERIC: Gas anomaly, no facility match
  - CONFIRMED_UNREGISTERED  : Both thermal AND atmospheric, no facility match
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.gem_service import is_in_brick_kiln_belt, is_in_coalfield_fire_zone

# Thresholds for triggering an unregistered-activity alert
THERMAL_CONFIDENCE_THRESHOLD = 0.65   # ML confidence for thermal flag
ATMOS_Z_THRESHOLD_UNREGISTERED = 2.5  # More lenient than facility-matched (less context)
FACILITY_MATCH_RADIUS_M = 3000        # Must be >3km from any complex to be "unregistered"


def classify_unregistered(
    db: Session,
    event_id: int,
    lat: float,
    lon: float,
    ml_class: int,
    ml_confidence: float,
    day_night: str,
    acquisition_date: str,     # YYYY-MM-DD for seasonal check
    complex_id: Optional[int], # None = no facility match
    atmos_max_z: float = 0.0,
) -> Optional[dict]:
    """
    Determine whether this event should raise an UNREGISTERED_ACTIVITY alert.

    Returns a dict with the alert classification, or None if the event
    is explained by a known facility or kiln pattern.

    Design decision: We return None (not suppress) for known facilities and
    kiln-belt seasonal events. We NEVER return None just because we're unsure;
    ambiguous cases with high confidence and no facility match get escalated.
    """
    # ── Step 1: Is there a facility match? ────────────────────────────────────
    if complex_id is not None:
        return None   # Known facility — handled by main classification

    # ── Step 2: Brick kiln belt check ─────────────────────────────────────────
    try:
        month = int(acquisition_date.split("-")[1]) if acquisition_date else datetime.utcnow().month
    except (ValueError, IndexError):
        month = datetime.utcnow().month

    if is_in_brick_kiln_belt(lat, lon, month):
        # This is likely a seasonal brick kiln — not an unregistered anomaly
        return {
            "event_id": event_id,
            "alert_type": "SEASONAL_KILN_ACTIVITY",
            "priority": "LOW",
            "explanation": (
                f"Location ({lat:.3f}, {lon:.3f}) is within the Indo-Gangetic Plains "
                f"brick kiln belt during active season (month {month}). "
                f"Intermittent thermal signal consistent with kiln campaign firing. "
                f"Not escalated as unregistered activity."
            ),
            "requires_investigation": False,
        }

    # ── Step 3: Coal-seam fire zone ───────────────────────────────────────────
    if is_in_coalfield_fire_zone(lat, lon):
        return {
            "event_id": event_id,
            "alert_type": "COAL_SEAM_FIRE",
            "priority": "LOW",
            "explanation": (
                f"Location ({lat:.3f}, {lon:.3f}) falls within the Jharia coalfield "
                f"coal-seam fire zone. Persistent thermal signal expected; "
                f"already catalogued in GEM database. Not an unregistered anomaly."
            ),
            "requires_investigation": False,
        }

    # ── Step 4: Is the thermal signal strong enough to flag? ──────────────────
    has_strong_thermal = (
        ml_class in {2, 3}
        and ml_confidence >= THERMAL_CONFIDENCE_THRESHOLD
    )
    has_atmospheric = atmos_max_z >= ATMOS_Z_THRESHOLD_UNREGISTERED
    is_nighttime = str(day_night).upper().strip() == "N"

    if not has_strong_thermal and not has_atmospheric:
        return None   # Weak signal, not enough evidence to escalate

    # ── Step 5: Determine alert category ─────────────────────────────────────
    if has_strong_thermal and has_atmospheric:
        alert_type = "CONFIRMED_UNREGISTERED"
        priority = "CRITICAL"
        explanation = (
            f"UNREGISTERED ACTIVITY — CRITICAL: Both thermal (ml_class={ml_class}, "
            f"confidence={ml_confidence:.2f}) and atmospheric (max_Z={atmos_max_z:.2f}) "
            f"anomalies detected at ({lat:.4f}, {lon:.4f}) with no matching facility "
            f"within {FACILITY_MATCH_RADIUS_M}m. Two independent channels agree. "
            f"{'Nighttime detection strengthens signal. ' if is_nighttime else ''}"
            f"Possible: unregistered factory, illegal gas flare, or unauthorized industrial operation."
        )
    elif has_strong_thermal:
        alert_type = "UNREGISTERED_THERMAL"
        priority = "HIGH"
        explanation = (
            f"UNREGISTERED THERMAL SOURCE: High-confidence thermal event "
            f"(ml_class={ml_class}, confidence={ml_confidence:.2f}) at "
            f"({lat:.4f}, {lon:.4f}) with no registered facility within "
            f"{FACILITY_MATCH_RADIUS_M}m. "
            f"{'Nighttime detection. ' if is_nighttime else ''}"
            f"Possible: unregistered brick kiln (outside known belt), "
            f"illegal open burning, or small-scale industrial operation."
        )
    else:  # atmospheric only
        alert_type = "UNREGISTERED_ATMOSPHERIC"
        priority = "HIGH"
        explanation = (
            f"UNREGISTERED ATMOSPHERIC ANOMALY: Gas anomaly "
            f"(max_Z={atmos_max_z:.2f}) detected at ({lat:.4f}, {lon:.4f}) "
            f"with no registered facility within {FACILITY_MATCH_RADIUS_M}m "
            f"and no matching thermal signature. "
            f"Possible: gas leak from unregistered infrastructure or natural seep."
        )

    return {
        "event_id": event_id,
        "alert_type": alert_type,
        "priority": priority,
        "lat": lat,
        "lon": lon,
        "ml_class": ml_class,
        "ml_confidence": ml_confidence,
        "atmos_max_z": atmos_max_z,
        "is_nighttime": is_nighttime,
        "explanation": explanation,
        "requires_investigation": True,
    }


def get_unregistered_geojson(db: Session) -> dict:
    """
    Return all unregistered-activity alerts from FusedEventScore as GeoJSON.
    Used by the frontend's unregistered-activity map layer.
    """
    sql = text("""
        SELECT
            fs.event_id,
            fe.latitude,
            fe.longitude,
            fs.alert_category,
            fs.fused_score,
            fs.signal_agreement,
            fs.explanation,
            fe.day_night,
            ef.ml_class,
            ef.ml_confidence
        FROM fused_event_scores fs
        JOIN firms_events fe ON fe.event_id = fs.event_id
        JOIN event_features ef ON ef.event_id = fs.event_id
        WHERE fs.alert_category LIKE '%UNREGISTERED%'
        ORDER BY fs.fused_score DESC
        LIMIT 500
    """)

    try:
        rows = db.execute(sql).fetchall()
    except Exception as e:
        return {"type": "FeatureCollection", "features": [], "error": str(e)}

    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row[2]), float(row[1])],
            },
            "properties": {
                "event_id": int(row[0]),
                "alert_category": row[3],
                "fused_score": float(row[4]) if row[4] else None,
                "signal_agreement": row[5],
                "explanation": row[6],
                "is_nighttime": str(row[7]).upper() == "N",
                "ml_class": int(row[8]) if row[8] is not None else None,
                "ml_confidence": float(row[9]) if row[9] else None,
            },
        })

    return {"type": "FeatureCollection", "features": features}


def get_unregistered_summary(db: Session) -> dict:
    """Summary counts by alert type for the API."""
    sql = text("""
        SELECT alert_category, COUNT(*) as cnt
        FROM fused_event_scores
        WHERE alert_category LIKE '%UNREGISTERED%'
           OR alert_category LIKE '%KILN%'
           OR alert_category LIKE '%COAL_SEAM%'
        GROUP BY alert_category
    """)
    try:
        rows = db.execute(sql).fetchall()
        by_type = {str(r[0]): int(r[1]) for r in rows}
        return {
            "counts_by_type": by_type,
            "total": sum(by_type.values()),
        }
    except Exception as e:
        return {"error": str(e), "total": 0}
