from sqlalchemy.orm import Session
from app.models.alert import Alert
from app.models.features import EventFeature
from app.models.firms import FirmsEvent
from app.api.classifications import CLASS_MAPPING

# Configurable thresholds
ALERT_CONFIG = {
    "target_class": 3, # Abnormal Industrial Thermal Event
    "min_abnormality_z": 2.5,
    "min_confidence": 0.85
}

def evaluate_and_create_alert(event_id: int, db: Session):
    """
    Evaluates if an event warrants an alert and creates it in the DB.
    Trigger condition: 
    - Classification matches target_class (default: 3)
    - Abnormality (robust_frp_z) exceeds min_abnormality_z (default: 2.5)
    """
    feature = db.query(EventFeature).filter(EventFeature.event_id == event_id).first()
    if not feature:
        return None
        
    event = db.query(FirmsEvent).filter(FirmsEvent.event_id == event_id).first()
    if not event:
        return None

    # Check if alert already exists
    existing_alert = db.query(Alert).filter(Alert.event_id == event_id).first()
    if existing_alert:
        return existing_alert

    # Condition: Matches target class, exceeds thermal abnormality threshold, AND confidence > threshold
    if feature.ml_class == ALERT_CONFIG["target_class"] and feature.robust_frp_z > ALERT_CONFIG["min_abnormality_z"] and feature.ml_confidence > ALERT_CONFIG["min_confidence"]:
        class_name = CLASS_MAPPING.get(feature.ml_class, "Unknown")
        
        # Create Alert
        alert = Alert(
            event_id=event_id,
            title="Suspected Abnormal Industrial Thermal Event",
            facility=f"Industrial Site near {feature.distance_to_industry_m:.0f}m" if feature.distance_to_industry_m is not None else "Unknown Facility",
            classification=class_name,
            confidence=feature.ml_confidence,
            risk="HIGH",
            frp=event.frp,
            baseline_frp=feature.median_historical_frp,
            frp_ratio=feature.frp_ratio_to_baseline,
            latitude=event.latitude,
            longitude=event.longitude
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert
        
    return None

def trigger_all_alerts(db: Session):
    """
    Utility for the prototype to evaluate all events for alerts.
    """
    features = db.query(EventFeature).all()
    created_alerts = []
    for f in features:
        alert = evaluate_and_create_alert(f.event_id, db)
        if alert:
            created_alerts.append(alert)
    return created_alerts
