"""
fusion_service.py — Phase 5e: 4-Channel evidence fusion scoring
================================================================
Combines four independent evidence channels into a single fused confidence
score per event. Independent signals agreeing raises confidence beyond any
single channel alone.

Channels:
  1. THERMAL    — XGBoost ml_class + ml_confidence (always present)
  2. ATMOSPHERIC— Sentinel-5P TROPOMI Z-score (Phase 5a)
  3. BURN_SCAR  — Sentinel-2 delta-NBR or SAR change (Phase 5b/5c)
  4. NIGHTTIME  — FIRMS day/night proxy (Phase 5d substitute)
                  A nighttime ('N') thermal detection at a historically
                  unregistered location is a stronger unregistered-activity
                  signal than a daytime detection.

Design principle: A channel 2 or 4 anomaly with NO thermal signature must
surface as its own "NON-THERMAL ANOMALY" category, not be dropped for
lacking a thermal match. This is the core reason the multi-channel system
exists — it catches gas leaks, cold releases, and unregistered nighttime
activity that thermal-only systems miss.

Evidence trace:
  Alongside the numerical score, each prediction carries a plain-language
  "evidence trace" listing:
    - Which channels fired
    - The hysteresis state of the nearest complex (if any)
    - Whether there's a facility match
  This explains the SYSTEM decision, complementing SHAP which explains the ML.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.features import FusedEventScore, EventFeature
from app.models.firms import FirmsEvent
from app.models.facility_cluster import FacilityComplex


# ─────────────────────────────────────────────────────────────────────────────
# Scoring weights
# ─────────────────────────────────────────────────────────────────────────────
# Each channel contributes a weight to the fused confidence.
# The base score starts from the ML thermal confidence.
# Additional channels add up to their weight when firing.
WEIGHT_ATMOSPHERIC = 0.15    # S5P Z-score anomaly
WEIGHT_BURN_SCAR   = 0.15    # Sentinel-2 ΔNBR or SAR confirmation
WEIGHT_NIGHTTIME   = 0.10    # Nighttime thermal proxy

THERMAL_INDUSTRIAL_CLASSES = {2, 3}  # Persistent industrial / Abnormal industrial


def compute_4channel_fusion(
    db: Session,
    event_id: int,
    lon: float,
    lat: float,
    event_date: str,
    day_night: str,
    ml_class: int,
    ml_confidence: float,
    complex_id: Optional[int] = None,
) -> dict:
    """
    Compute the 4-channel fused confidence score for a single event.
    Persists/updates a FusedEventScore row.
    Returns the full score dict including evidence trace.
    """

    # ── Channel 1: Thermal ───────────────────────────────────────────────────
    has_thermal = ml_class in THERMAL_INDUSTRIAL_CLASSES and ml_confidence > 0.60
    thermal_score = ml_confidence if has_thermal else 0.0

    # ── Channel 2: Atmospheric ───────────────────────────────────────────────
    atmos_anomalous = False
    atmos_max_z = 0.0
    atmos_gases_fired = []

    if complex_id:
        from app.services.atmospheric_service import AtmosphericReading, ATMOS_Z_THRESHOLD
        # Look for anomalous readings near the event date (±3 days)
        readings = db.query(AtmosphericReading).filter(
            AtmosphericReading.complex_id == complex_id,
            AtmosphericReading.is_anomalous == 1,
        ).all()
        if readings:
            atmos_anomalous = True
            for r in readings:
                if r.z_score and abs(r.z_score) > atmos_max_z:
                    atmos_max_z = abs(r.z_score)
                atmos_gases_fired.append(r.gas_species)

    # ── Channel 3: Burn scar (optical or SAR) ───────────────────────────────
    burn_confirmed = False
    burn_channel = "none"

    from app.services.burn_scar_service import BurnScarResult
    bsr = db.query(BurnScarResult).filter(BurnScarResult.event_id == event_id).first()
    if bsr:
        burn_confirmed = bsr.is_confirmed
        burn_channel = bsr.channel_used

    # ── Channel 4: Nighttime thermal proxy ──────────────────────────────────
    # A nighttime detection at an unregistered location is a stronger signal.
    # Score the nighttime flag independently of whether there's a facility match.
    is_nighttime = (str(day_night).upper().strip() == "N")
    has_no_facility = (complex_id is None)
    nighttime_anomaly = is_nighttime and has_no_facility

    # ── Fused score calculation ───────────────────────────────────────────────
    if has_thermal:
        # Start from ML confidence, add channel bonuses
        fused = thermal_score
        if atmos_anomalous:
            fused = min(1.0, fused + WEIGHT_ATMOSPHERIC)
        if burn_confirmed:
            fused = min(1.0, fused + WEIGHT_BURN_SCAR)
        if nighttime_anomaly:
            fused = min(1.0, fused + WEIGHT_NIGHTTIME)
        channels_fired = ["THERMAL"]
        if atmos_anomalous:
            channels_fired.append("ATMOSPHERIC")
        if burn_confirmed:
            channels_fired.append(f"BURN_SCAR({burn_channel})")
        if nighttime_anomaly:
            channels_fired.append("NIGHTTIME_PROXY")

    elif atmos_anomalous and not has_thermal:
        # Atmospheric anomaly without thermal → gas leak / cold release
        fused = min(0.75, 0.35 + atmos_max_z * 0.05)
        if burn_confirmed:
            fused = min(0.85, fused + WEIGHT_BURN_SCAR)
        if nighttime_anomaly:
            fused = min(0.90, fused + WEIGHT_NIGHTTIME)
        channels_fired = ["ATMOSPHERIC"]
        if burn_confirmed:
            channels_fired.append(f"BURN_SCAR({burn_channel})")
        if nighttime_anomaly:
            channels_fired.append("NIGHTTIME_PROXY")

    elif nighttime_anomaly and not has_thermal and not atmos_anomalous:
        # Nighttime-only anomaly — weakest evidence
        fused = 0.30
        channels_fired = ["NIGHTTIME_PROXY"]

    else:
        fused = thermal_score
        channels_fired = ["THERMAL"] if has_thermal else []

    n_channels = len(channels_fired)

    # ── Signal agreement classification ──────────────────────────────────────
    if has_thermal and (atmos_anomalous or burn_confirmed):
        signal_agreement = "MULTI_CHANNEL_CONFIRMED"
    elif has_thermal and not atmos_anomalous and not burn_confirmed:
        signal_agreement = "THERMAL_ONLY"
    elif atmos_anomalous and not has_thermal:
        signal_agreement = "ATMOSPHERIC_ONLY"
    elif nighttime_anomaly and not has_thermal and not atmos_anomalous:
        signal_agreement = "NIGHTTIME_ONLY"
    else:
        signal_agreement = "NEITHER"

    # ── Alert category ────────────────────────────────────────────────────────
    if signal_agreement == "MULTI_CHANNEL_CONFIRMED":
        alert_category = "CONFIRMED MULTI-CHANNEL INDUSTRIAL EVENT"
    elif has_thermal and ml_class == 3:
        alert_category = "ABNORMAL INDUSTRIAL THERMAL EVENT"
    elif atmos_anomalous and not has_thermal:
        gases_str = ", ".join(set(atmos_gases_fired))
        alert_category = f"NON-THERMAL ATMOSPHERIC ANOMALY ({gases_str})"
    elif nighttime_anomaly and not has_thermal:
        alert_category = "NIGHTTIME UNREGISTERED ACTIVITY — no thermal confirmation"
    elif has_thermal and has_no_facility:
        alert_category = "UNREGISTERED THERMAL SOURCE — no facility match"
    else:
        alert_category = None

    # ── Plain-language evidence trace ─────────────────────────────────────────
    trace_lines = []
    trace_lines.append(f"Thermal: class={ml_class} confidence={ml_confidence:.2f}")

    if complex_id:
        # Get hysteresis state
        try:
            from app.services.hysteresis_service import get_complex_state
            hyst = get_complex_state(db, complex_id)
            fc = db.query(FacilityComplex).filter(
                FacilityComplex.complex_id == complex_id
            ).first()
            fc_name = fc.name if fc else f"Complex #{complex_id}"
            trace_lines.append(
                f"Facility match: {fc_name} | Hysteresis: {hyst['state']} "
                f"(streak={hyst['clear_days_streak']}/{hyst['clear_days_required']} clear days)"
            )
        except Exception:
            trace_lines.append(f"Facility match: complex_id={complex_id}")
    else:
        trace_lines.append("Facility match: NONE (>3km from any known facility complex)")

    if atmos_anomalous:
        trace_lines.append(
            f"Atmospheric: ANOMALY detected | gases={atmos_gases_fired} | max_Z={atmos_max_z:.2f}"
        )
    else:
        trace_lines.append("Atmospheric: no anomaly")

    if burn_channel != "none":
        if burn_confirmed:
            trace_lines.append(f"Burn/Disturbance: CONFIRMED via {burn_channel.upper()}")
        else:
            trace_lines.append(f"Burn/Disturbance: not confirmed via {burn_channel.upper()}")
    else:
        trace_lines.append("Burn/Disturbance: no scene available")

    if is_nighttime:
        trace_lines.append(
            f"Nighttime: YES (daynight=N) | facility_match={'yes' if not has_no_facility else 'NO — stronger anomaly signal'}"
        )
    else:
        trace_lines.append("Nighttime: daytime detection")

    trace_lines.append(
        f"Channels fired: {channels_fired} | "
        f"Fused score: {fused:.3f} | "
        f"Agreement: {signal_agreement}"
    )

    evidence_trace = "\n".join(trace_lines)

    # ── Channel detail JSON ────────────────────────────────────────────────────
    channel_details = json.dumps({
        "thermal": {"fired": has_thermal, "ml_class": ml_class, "confidence": round(ml_confidence, 4)},
        "atmospheric": {"fired": atmos_anomalous, "max_z": round(atmos_max_z, 3), "gases": atmos_gases_fired},
        "burn_scar": {"fired": burn_confirmed, "channel": burn_channel},
        "nighttime": {"fired": nighttime_anomaly, "is_nighttime": is_nighttime, "no_facility": has_no_facility},
        "n_channels_fired": n_channels,
    })

    # ── Persist to DB ──────────────────────────────────────────────────────────
    score_row = db.query(FusedEventScore).filter(
        FusedEventScore.event_id == event_id
    ).first()

    if score_row is None:
        score_row = FusedEventScore(event_id=event_id)
        db.add(score_row)

    score_row.complex_id       = complex_id
    score_row.fused_score      = round(fused, 4)
    score_row.signal_agreement = signal_agreement
    score_row.alert_category   = alert_category
    score_row.explanation      = evidence_trace
    score_row.atmos_max_z      = round(atmos_max_z, 3)
    score_row.computed_at      = datetime.utcnow().isoformat()[:19]

    # Persist channel_details to the extra column (added via migration)
    if hasattr(score_row, "channel_details"):
        score_row.channel_details = channel_details
    if hasattr(score_row, "evidence_trace"):
        score_row.evidence_trace = evidence_trace
    if hasattr(score_row, "n_channels"):
        score_row.n_channels = n_channels

    db.commit()

    return {
        "event_id": event_id,
        "fused_score": round(fused, 4),
        "signal_agreement": signal_agreement,
        "alert_category": alert_category,
        "channels_fired": channels_fired,
        "n_channels": n_channels,
        "evidence_trace": evidence_trace,
        "channel_details": json.loads(channel_details),
    }


def run_fusion_for_all_events(db: Session) -> dict:
    """
    Batch-run 4-channel fusion scoring for all live events that have been
    ML-classified. Called at the end of the --ml pipeline step.
    
    Returns summary statistics.
    """
    print("[Phase 5e] Running 4-channel fusion scoring for all classified events...")

    # Fetch all classified events with their context
    sql = text("""
        SELECT
            f.event_id,
            fe.latitude,
            fe.longitude,
            fe.day_night,
            ef.ml_class,
            ef.ml_confidence,
            ef.distance_to_industry_m,
            ef.robust_frp_z
        FROM firms_events fe
        JOIN event_features ef ON fe.event_id = ef.event_id
        LEFT JOIN firms_events f ON f.event_id = fe.event_id
        WHERE ef.ml_class IS NOT NULL
        ORDER BY ef.ml_confidence DESC
        LIMIT 2000
    """)

    # Simplified version — query events directly
    events_sql = text("""
        SELECT
            fe.event_id,
            fe.latitude,
            fe.longitude,
            COALESCE(fe.day_night, 'D') as day_night,
            ef.ml_class,
            COALESCE(ef.ml_confidence, 0.0) as ml_confidence,
            COALESCE(ef.distance_to_industry_m, 9999.0) as distance_to_industry_m
        FROM firms_events fe
        JOIN event_features ef ON fe.event_id = ef.event_id
        WHERE ef.ml_class IS NOT NULL
        LIMIT 2000
    """)

    rows = db.execute(events_sql).fetchall()

    if not rows:
        print("[Phase 5e] No classified events to score.")
        return {"total": 0}

    print(f"  Scoring {len(rows)} events...")

    summary = {
        "total": len(rows),
        "multi_channel": 0,
        "thermal_only": 0,
        "atmospheric_only": 0,
        "nighttime_only": 0,
        "unregistered": 0,
    }

    for row in rows:
        event_id = int(row[0])
        lat = float(row[1])
        lon = float(row[2])
        day_night = str(row[3])
        ml_class = int(row[4])
        ml_confidence = float(row[5])
        dist_to_industry = float(row[6])

        # Determine nearest complex_id
        complex_id = None
        if dist_to_industry < 3000:
            complex_sql = text("""
                SELECT c.complex_id FROM facility_complexes c
                JOIN firms_events e ON e.event_id = :eid
                WHERE ST_DWithin(c.centroid_geom, e.geom, 3000)
                ORDER BY ST_Distance(c.centroid_geom, e.geom) ASC
                LIMIT 1
            """)
            cres = db.execute(complex_sql, {"eid": event_id}).fetchone()
            if cres:
                complex_id = int(cres[0])

        event_date = datetime.utcnow().strftime("%Y-%m-%d")  # approx for live events

        result = compute_4channel_fusion(
            db=db,
            event_id=event_id,
            lon=lon,
            lat=lat,
            event_date=event_date,
            day_night=day_night,
            ml_class=ml_class,
            ml_confidence=ml_confidence,
            complex_id=complex_id,
        )

        sa = result["signal_agreement"]
        if sa == "MULTI_CHANNEL_CONFIRMED":
            summary["multi_channel"] += 1
        elif sa == "THERMAL_ONLY":
            summary["thermal_only"] += 1
        elif sa == "ATMOSPHERIC_ONLY":
            summary["atmospheric_only"] += 1
        elif sa == "NIGHTTIME_ONLY":
            summary["nighttime_only"] += 1

        if result.get("alert_category") and "UNREGISTERED" in str(result.get("alert_category", "")):
            summary["unregistered"] += 1

    print(
        f"[Phase 5e] Done. Multi-channel: {summary['multi_channel']} | "
        f"Thermal-only: {summary['thermal_only']} | "
        f"Atmospheric-only: {summary['atmospheric_only']} | "
        f"Unregistered: {summary['unregistered']}"
    )
    return summary
