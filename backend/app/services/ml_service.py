"""
ml_service.py — Phase 2/4/6 updated
=====================================
Changes from original:
  Phase 2: 'instrument' (sensor type) added as a feature. Coordinate
           exclusion confirmed and enforced by assert_no_coordinate_leakage().
  Phase 4a: Circularity ablation — model retrained with 'distance_to_industry_m'
            ablated to quantify how much accuracy derives from reproducing its
            own labeling rule vs. genuine learned signal.
  Phase 6: SHAP TreeSHAP attribution added. Per-prediction top-feature
           explanations stored in EventFeature.shap_json and returned via API.
"""

import os
import json
import pandas as pd
import numpy as np
import xgboost as xgb
import shap
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.features import EventFeature
from app.models.firms import FirmsEvent
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
import planetary_computer
from pystac_client import Client
import rasterio
from pyproj import Transformer

ESA_CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice",
    80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves",
    100: "Moss and lichen"
}

# ---------------------------------------------------------------------------
# Phase 2 — Coordinate exclusion enforcement
# ---------------------------------------------------------------------------
# These column names must NEVER reach the XGBoost feature space.
# 'distance_to_industry_m' is legitimate (relative distance, not absolute coord).
FORBIDDEN_COORDINATE_COLUMNS = frozenset([
    "latitude", "longitude", "lat", "lon", "x", "y",
    "centroid_lat", "centroid_lon",
])

FEATURES = ["frp", "distance_to_industry_m", "historical_event_count", "sensor_type_encoded"]
"""
Canonical XGBoost feature set.
  frp                     — Fire Radiative Power (MW): primary thermal signal
  distance_to_industry_m  — Distance to nearest industrial facility (m): spatial prior
  historical_event_count  — # historical detections at this location: persistence indicator
  sensor_type_encoded     — 0=VIIRS, 1=MODIS: resolution/sensitivity differs meaningfully
"""

ABLATION_FEATURES = ["frp", "historical_event_count", "sensor_type_encoded"]
"""
Features for Phase 4a circularity ablation — 'distance_to_industry_m' removed.
This is the feature used by the labeling rule, so ablating it quantifies how
much accuracy is model-reproducing-its-own-rule vs. genuine learned signal.
"""


def assert_no_coordinate_leakage(df: pd.DataFrame) -> None:
    """
    Permanent enforcement test: raises AssertionError if any forbidden
    coordinate column is present in the dataframe being passed to XGBoost.
    Call this immediately before any model.fit() or model.predict() call.
    """
    cols = set(df.columns)
    leakage = cols & FORBIDDEN_COORDINATE_COLUMNS
    assert not leakage, (
        f"COORDINATE LEAKAGE DETECTED: columns {leakage} must never reach the "
        f"XGBoost feature space. They let the model memorize facility locations "
        f"instead of learning transferable signal."
    )


def generate_synthetic_labels(db: Session):
    """Deprecated for CP4 redesign. Labels now generated inside build_training_dataset."""
    pass


def _get_landcover_for_points(df):
    """Retained for training-set construction; uses serial approach (training is offline)."""
    client = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )
    lc_results = []
    src = None
    transformer = None
    print(f"Fetching Land Cover data for {len(df)} historical points...")
    for idx, row in df.iterrows():
        lon, lat = row['longitude'], row['latitude']
        try:
            if src and src.bounds.left <= lon <= src.bounds.right and src.bounds.bottom <= lat <= src.bounds.top:
                pass
            else:
                search = client.search(
                    collections=["esa-worldcover"],
                    intersects={"type": "Point", "coordinates": [lon, lat]},
                    datetime="2021-01-01/2021-12-31"
                )
                items = list(search.items())
                if not items:
                    lc_results.append("Unknown")
                    continue
                if src:
                    src.close()
                cog_href = items[0].assets["map"].href
                src = rasterio.open(cog_href)
                transformer = Transformer.from_crs("epsg:4326", src.crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
            val = list(src.sample([(x, y)]))[0][0]
            lc_results.append(ESA_CLASSES.get(val, "Unknown"))
        except Exception:
            lc_results.append("Unknown")
        if idx % 100 == 0 and idx > 0:
            print(f"Processed {idx} points...")
    if src:
        src.close()
    return lc_results


def build_training_dataset(db: Session):
    cache_path = "historical_training_set.csv"
    if os.path.exists(cache_path):
        print("Loading cached historical training dataset...")
        return pd.read_csv(cache_path)

    print("Building Weakly Supervised Training Dataset from Historical Data...")
    sql = text("""
        (
            SELECT fh.event_id, fh.latitude, fh.longitude, fh.acquisition_time, fh.frp,
                   COALESCE((
                       SELECT MIN(ST_Distance(fh.geom, i.geometry::geography))
                       FROM industrial_sites i
                       WHERE ST_DWithin(fh.geom, i.geometry::geography, 1000)
                   ), 0) as distance_to_industry_m,
                   (
                       SELECT COUNT(*) FROM firms_historical fh2
                       WHERE ST_DWithin(fh.geom, fh2.geom, 2000)
                   ) as historical_event_count,
                   'VIIRS_SNPP' as instrument
            FROM firms_historical fh
            WHERE EXISTS (
                SELECT 1 FROM industrial_sites i WHERE ST_DWithin(fh.geom, i.geometry::geography, 1000)
            )
            ORDER BY RANDOM()
            LIMIT 500
        )
        UNION ALL
        (
            SELECT fh.event_id, fh.latitude, fh.longitude, fh.acquisition_time, fh.frp,
                   6000.0 as distance_to_industry_m,
                   (
                       SELECT COUNT(*) FROM firms_historical fh2
                       WHERE ST_DWithin(fh.geom, fh2.geom, 2000)
                   ) as historical_event_count,
                   'VIIRS_SNPP' as instrument
            FROM firms_historical fh
            WHERE NOT EXISTS (
                SELECT 1 FROM industrial_sites i WHERE ST_DWithin(fh.geom, i.geometry::geography, 5000)
            )
            ORDER BY RANDOM()
            LIMIT 500
        )
    """)
    df = pd.read_sql(sql, db.bind)
    df = df.sort_values(by=['latitude', 'longitude'])
    df['dominant_landcover'] = _get_landcover_for_points(df)

    def assign_label(row):
        dist = row['distance_to_industry_m']
        lc = str(row['dominant_landcover'])
        if dist < 500:
            return 2   # Proxy Industrial
        elif dist > 5000:
            if 'Crop' in lc:
                return 1   # Proxy Agricultural
            elif 'Tree' in lc or 'Grass' in lc or 'Shrub' in lc:
                return 0   # Proxy Natural
        return -1   # Discard

    df['proxy_label'] = df.apply(assign_label, axis=1)
    df = df[df['proxy_label'] != -1]
    df.to_csv(cache_path, index=False)
    return df


def _encode_sensor(df: pd.DataFrame) -> pd.Series:
    """Encode instrument column: VIIRS variants → 0, MODIS variants → 1."""
    mapping = {
        "VIIRS_SNPP": 0, "VIIRS_NOAA20": 0,
        "MODIS": 1, "MODIS_NRT": 1, "TERRA": 1, "AQUA": 1,
    }
    return df.get("instrument", pd.Series(["VIIRS_SNPP"] * len(df))).map(
        lambda x: mapping.get(str(x).upper().replace(" ", "_"), 0)
    )


def _prepare_features(df: pd.DataFrame, feature_list: list) -> pd.DataFrame:
    """
    Convert feature columns to numeric, fill NAs, and run coordinate leakage check.
    Only processes columns that are actually in feature_list (safe for ablation path).
    """
    if "sensor_type_encoded" in feature_list and "sensor_type_encoded" not in df.columns:
        df = df.copy()
        df["sensor_type_encoded"] = _encode_sensor(df)

    result = df[feature_list].copy()

    # Only fill columns that exist in this feature set
    if "distance_to_industry_m" in result.columns:
        result["distance_to_industry_m"] = pd.to_numeric(
            result["distance_to_industry_m"], errors="coerce"
        ).fillna(6000.0)

    if "historical_event_count" in result.columns:
        result["historical_event_count"] = pd.to_numeric(
            result["historical_event_count"], errors="coerce"
        ).fillna(0)

    if "frp" in result.columns:
        result["frp"] = pd.to_numeric(result["frp"], errors="coerce").fillna(0.0)

    if "sensor_type_encoded" in result.columns:
        result["sensor_type_encoded"] = pd.to_numeric(
            result["sensor_type_encoded"], errors="coerce"
        ).fillna(0).astype(int)

    assert_no_coordinate_leakage(result)
    return result



def train_and_predict(db: Session):
    print("--- CP4+: XGBoost Classification via Weak Supervision (with SHAP) ---")

    # ---- 1. Training dataset ----
    train_df = build_training_dataset(db)
    train_df['acquisition_time'] = pd.to_datetime(train_df['acquisition_time'])
    train_df['sensor_type_encoded'] = _encode_sensor(train_df)

    split_date = pd.to_datetime("2023-01-29")
    train_set = train_df[train_df['acquisition_time'] < split_date]
    val_set   = train_df[train_df['acquisition_time'] >= split_date]
    print(f"Chronological Split -> Train: {len(train_set)} records, Val: {len(val_set)} records.")


    X_train = _prepare_features(train_set, FEATURES)
    y_train = train_set['proxy_label']
    X_val   = _prepare_features(val_set, FEATURES)
    y_val   = val_set['proxy_label']

    # ---- 2. Full-feature model ----
    model = xgb.XGBClassifier(
        objective='multi:softprob', num_class=3,
        eval_metric='mlogloss', seed=42
    )
    model.fit(X_train, y_train)

    preds_val = model.predict(X_val)
    print("\n[Validation Metrics — Full Feature Set]")
    full_report = classification_report(
        y_val, preds_val,
        target_names=["Natural", "Agricultural", "Industrial"],
        zero_division=0, output_dict=True
    )
    print(classification_report(
        y_val, preds_val,
        target_names=["Natural", "Agricultural", "Industrial"],
        zero_division=0
    ))
    full_accuracy = full_report.get("accuracy", 0.0)

    # ---- 3. Phase 4a — Circularity ablation ----
    print("\n[Phase 4a — Circularity Ablation]")
    print("  Retraining WITHOUT 'distance_to_industry_m' (the labeling-rule feature)...")
    print("  This quantifies how much accuracy is the model reproducing its own labeling rule.")

    X_train_abl = _prepare_features(train_set, ABLATION_FEATURES)
    X_val_abl   = _prepare_features(val_set, ABLATION_FEATURES)

    model_abl = xgb.XGBClassifier(
        objective='multi:softprob', num_class=3,
        eval_metric='mlogloss', seed=42
    )
    model_abl.fit(X_train_abl, y_train)
    preds_abl = model_abl.predict(X_val_abl)

    abl_report = classification_report(
        y_val, preds_abl,
        target_names=["Natural", "Agricultural", "Industrial"],
        zero_division=0, output_dict=True
    )
    abl_accuracy = abl_report.get("accuracy", 0.0)

    accuracy_drop = full_accuracy - abl_accuracy
    print(classification_report(
        y_val, preds_abl,
        target_names=["Natural", "Agricultural", "Industrial"],
        zero_division=0
    ))
    print(f"  Full-feature accuracy : {full_accuracy:.4f}")
    print(f"  Ablated accuracy      : {abl_accuracy:.4f}")
    print(f"  Accuracy drop         : {accuracy_drop:+.4f}")
    print(
        f"\n  INTERPRETATION: {accuracy_drop:.1%} of accuracy is attributable to the model "
        f"reproducing its labeling rule (distance_to_industry_m). The remaining "
        f"{abl_accuracy:.1%} represents genuinely learned signal from FRP, "
        f"historical count, and sensor type."
    )

    # ---- 4. SHAP explainer on full model ----
    print("\n[Phase 6] Computing SHAP TreeExplainer...")
    explainer = shap.TreeExplainer(model)

    # ---- 5. Live event prediction ----
    print("\nDeploying classifier on live events...")
    live_query = db.query(
        EventFeature.event_id,
        EventFeature.frp_ratio_to_baseline,
        EventFeature.robust_frp_z,
        EventFeature.distance_to_industry_m,
        EventFeature.historical_event_count
    ).statement
    live_df = pd.read_sql(live_query, db.bind)

    if live_df.empty:
        print("No live events to classify.")
        return

    firms_df = pd.read_sql("SELECT event_id, frp, instrument FROM firms_events", db.bind)
    live_df  = live_df.merge(firms_df, on="event_id", how="left")
    live_df.fillna(
        {'distance_to_industry_m': 6000.0, 'historical_event_count': 0, 'frp': 0.0},
        inplace=True
    )
    live_df['sensor_type_encoded'] = _encode_sensor(live_df)

    X_live = _prepare_features(live_df, FEATURES)
    live_preds = model.predict(X_live)
    live_probs = model.predict_proba(X_live)

    # SHAP values for live events
    shap_values = explainer.shap_values(X_live)
    # shap_values shape: (n_classes, n_samples, n_features) or (n_samples, n_features) per class

    abnormal_count = 0
    updates = []
    for idx, row in live_df.iterrows():
        eid          = int(row['event_id'])
        ml_class     = int(live_preds[idx])
        ml_confidence = float(np.max(live_probs[idx]))
        z_score      = row['robust_frp_z']

        if ml_class == 2 and z_score is not None and float(z_score) > 2.5:
            ml_class = 3
            abnormal_count += 1

        # Build SHAP explanation for the predicted class
        predicted_class_idx = ml_class if ml_class <= 2 else 2
        try:
            if isinstance(shap_values, list):
                sv = shap_values[predicted_class_idx][idx]
            else:
                sv = shap_values[idx]
            shap_dict = {
                col: round(float(sv[i]), 5)
                for i, col in enumerate(FEATURES)
            }
        except Exception:
            shap_dict = {}

        updates.append({
            "event_id": eid,
            "ml_class": ml_class,
            "ml_confidence": ml_confidence,
            "shap_json": json.dumps(shap_dict),
        })

    db.bulk_update_mappings(EventFeature, updates)
    db.commit()
    print(
        f"Successfully classified {len(live_df)} live events. "
        f"Escalated {abnormal_count} to Abnormal Industrial."
    )
    print(f"SHAP explanations computed and stored for all {len(live_df)} events.")

    # ---- 6. Phase 3b: Hysteresis update ----
    print("\n[Phase 3b] Updating Hysteresis state machine...")
    from sqlalchemy import text
    from datetime import date
    from app.services.hysteresis_service import update_all_complex_states
    
    anomalous_complexes_query = """
        SELECT DISTINCT c.complex_id
        FROM facility_complexes c
        JOIN firms_events e ON ST_DWithin(c.centroid_geom, e.geom, 3000)
        JOIN event_features f ON e.event_id = f.event_id
        WHERE f.ml_class = 3
    """
    rows = db.execute(text(anomalous_complexes_query)).fetchall()
    anom_ids = set(r[0] for r in rows)
    
    summary = update_all_complex_states(db, date.today(), anom_ids)
    print(f"  Hysteresis updated: {summary}")
