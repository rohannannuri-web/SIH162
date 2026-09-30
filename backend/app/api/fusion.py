"""
fusion.py — Phase 8: 4-channel fusion score API endpoints
==========================================================
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.features import FusedEventScore

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/event/{event_id}")
def get_fusion_score(event_id: int, db: Session = Depends(get_db)):
    """
    Return the full 4-channel fused confidence score for a specific event,
    including the plain-language evidence trace.
    """
    score = db.query(FusedEventScore).filter(
        FusedEventScore.event_id == event_id
    ).first()

    if not score:
        return {
            "event_id": event_id,
            "fused_score": None,
            "signal_agreement": "NOT_COMPUTED",
            "alert_category": None,
            "explanation": (
                "Fusion scoring has not been run for this event. "
                "Run 'python init_db.py --fusion' to compute."
            ),
            "channel_details": None,
        }

    result = {
        "event_id": event_id,
        "fused_score": score.fused_score,
        "signal_agreement": score.signal_agreement,
        "alert_category": score.alert_category,
        "explanation": score.explanation,
        "atmos_max_z": score.atmos_max_z,
        "complex_id": score.complex_id,
        "computed_at": score.computed_at,
    }

    # Include channel details if the column exists
    if hasattr(score, "channel_details") and score.channel_details:
        import json
        try:
            result["channel_details"] = json.loads(score.channel_details)
        except Exception:
            result["channel_details"] = score.channel_details

    return result


@router.get("/geojson")
def get_fusion_geojson(min_score: float = 0.70, db: Session = Depends(get_db)):
    """
    Return all high-confidence fusion events as GeoJSON.
    Only returns events with fused_score >= min_score.
    """
    from sqlalchemy import text
    sql = text("""
        SELECT
            fs.event_id,
            fe.latitude,
            fe.longitude,
            fs.fused_score,
            fs.signal_agreement,
            fs.alert_category,
            fs.explanation
        FROM fused_event_scores fs
        JOIN firms_events fe ON fe.event_id = fs.event_id
        WHERE fs.fused_score >= :min_score
        ORDER BY fs.fused_score DESC
        LIMIT 500
    """)
    try:
        rows = db.execute(sql, {"min_score": min_score}).fetchall()
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
                "fused_score": float(row[3]) if row[3] else None,
                "signal_agreement": row[4],
                "alert_category": row[5],
                "explanation": row[6],
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/summary")
def get_fusion_summary(db: Session = Depends(get_db)):
    """
    Return aggregate statistics on the 4-channel fusion results.
    """
    from sqlalchemy import text
    sql = text("""
        SELECT
            signal_agreement,
            COUNT(*) as cnt,
            ROUND(AVG(fused_score)::numeric, 3) as avg_score
        FROM fused_event_scores
        GROUP BY signal_agreement
        ORDER BY cnt DESC
    """)
    try:
        rows = db.execute(sql).fetchall()
    except Exception as e:
        return {"error": str(e)}

    breakdown = [
        {"signal_agreement": r[0], "count": int(r[1]), "avg_fused_score": float(r[2])}
        for r in rows
    ]
    total = sum(b["count"] for b in breakdown)

    return {
        "total_scored": total,
        "breakdown": breakdown,
        "note": (
            "signal_agreement categories: MULTI_CHANNEL_CONFIRMED (2+ channels agree), "
            "THERMAL_ONLY, ATMOSPHERIC_ONLY, NIGHTTIME_ONLY, NEITHER."
        ),
    }
