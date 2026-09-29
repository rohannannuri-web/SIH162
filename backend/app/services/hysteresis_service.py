"""
hysteresis_service.py — Phase 3b: Hysteresis-based reclassification state machine
===================================================================================
Once a facility complex is classified ABNORMAL/ACCIDENTAL, it must show
HYSTERESIS_CLEAR_DAYS consecutive calendar days of non-anomalous detections
before it may reclassify back to ROUTINE (PERSISTENT_BASELINE).

HYSTERESIS_CLEAR_DAYS = 5  (configurable constant)

Tradeoff:
  Higher N → slower forgiveness, more resistant to long-duration events ageing
             into false normalcy (e.g. a 2-week industrial accident that would
             otherwise gradually absorb into the baseline).
  Lower N  → faster recovery after a genuine one-off event resolves, but weaker
             protection against extended accidents.
  N = 5 calendar days was chosen as the default: it spans a full Sentinel-2
  revisit cycle and enough FIRMS detection windows to distinguish a genuine
  trend reversal from random sensor noise.

States:
  ROUTINE    → normal baseline activity
  ABNORMAL   → active anomaly detected
  RECOVERING → anomaly cleared but not yet enough consecutive clear days
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.facility_cluster import FacilityComplex, FacilityHysteresisState

# ---------------------------------------------------------------------------
# Configurable constant
# ---------------------------------------------------------------------------
HYSTERESIS_CLEAR_DAYS = 5
"""
Consecutive calendar days of non-anomalous detections required before a
facility complex may reclassify from ABNORMAL/RECOVERING back to ROUTINE.

Tradeoff:
  ↑ N  → slower forgiveness, stronger protection against long-duration events
          ageing into false normalcy.
  ↓ N  → faster recovery, but weaker protection against sustained accidents.
"""


def _get_or_create_state(db: Session, complex_id: int) -> FacilityHysteresisState:
    state = db.query(FacilityHysteresisState).filter(
        FacilityHysteresisState.complex_id == complex_id
    ).first()
    if not state:
        state = FacilityHysteresisState(complex_id=complex_id, state="ROUTINE")
        db.add(state)
        db.flush()
    return state


def record_anomaly(db: Session, complex_id: int, detection_date: date) -> str:
    """
    Mark a facility complex as ABNORMAL on detection_date.
    Resets clear_days_streak.
    Returns new state name.
    """
    state = _get_or_create_state(db, complex_id)
    state.state              = "ABNORMAL"
    state.last_anomaly_date  = detection_date.isoformat()
    state.clear_days_streak  = 0
    state.total_abnormal_events = (state.total_abnormal_events or 0) + 1
    db.commit()
    return "ABNORMAL"


def record_clear_window(db: Session, complex_id: int, detection_date: date) -> str:
    """
    Record a non-anomalous detection window for a facility complex.
    Advances clear_days_streak by the number of days since the last clear window
    (or since the last anomaly if this is the first clear window).
    Transitions to ROUTINE only after HYSTERESIS_CLEAR_DAYS consecutive clear days.
    Returns current state name.
    """
    state = _get_or_create_state(db, complex_id)

    if state.state == "ROUTINE":
        return "ROUTINE"  # Nothing to do

    # Use the last known reference date: prefer a stored last_clear_date attribute.
    # Fall back to last_anomaly_date if no clear windows yet seen.
    last_ref_str = getattr(state, 'last_clear_date', None) or state.last_anomaly_date
    if last_ref_str:
        last_ref = date.fromisoformat(last_ref_str)
        days_increment = max(1, (detection_date - last_ref).days)
    else:
        days_increment = 1  # No reference date → count one day

    state.clear_days_streak = (state.clear_days_streak or 0) + days_increment

    # Update reference date for next call
    if hasattr(state, 'last_clear_date'):
        state.last_clear_date = detection_date.isoformat()

    if state.clear_days_streak >= HYSTERESIS_CLEAR_DAYS:
        state.state = "ROUTINE"
        state.clear_days_streak = 0
        db.commit()
        return "ROUTINE"
    else:
        state.state = "RECOVERING"
        db.commit()
        return "RECOVERING"



def get_complex_state(db: Session, complex_id: int) -> dict:
    """
    Return the full hysteresis state for a facility complex.
    Safe to call even if the complex has never been evaluated.
    """
    state = db.query(FacilityHysteresisState).filter(
        FacilityHysteresisState.complex_id == complex_id
    ).first()
    if not state:
        return {
            "complex_id": complex_id,
            "state": "ROUTINE",
            "last_anomaly_date": None,
            "clear_days_streak": 0,
            "clear_days_required": HYSTERESIS_CLEAR_DAYS,
            "total_abnormal_events": 0,
        }
    return {
        "complex_id": complex_id,
        "state": state.state,
        "last_anomaly_date": state.last_anomaly_date,
        "clear_days_streak": state.clear_days_streak,
        "clear_days_required": HYSTERESIS_CLEAR_DAYS,
        "total_abnormal_events": state.total_abnormal_events,
    }


def update_all_complex_states(db: Session, detection_date: date, anomalous_complex_ids: set[int]) -> dict:
    """
    Batch-update hysteresis states for all known facility complexes on detection_date.
    
    anomalous_complex_ids: set of complex_ids that had an anomalous detection today.
    All other known complexes get a clear-window tick.
    
    Returns a summary dict with counts per state transition.
    """
    all_complexes = db.query(FacilityComplex).all()
    summary = {"ROUTINE": 0, "ABNORMAL": 0, "RECOVERING": 0}

    for fc in all_complexes:
        if fc.complex_id in anomalous_complex_ids:
            new_state = record_anomaly(db, fc.complex_id, detection_date)
        else:
            new_state = record_clear_window(db, fc.complex_id, detection_date)
        summary[new_state] = summary.get(new_state, 0) + 1

    return summary
