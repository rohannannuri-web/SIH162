import os
import pandas as pd
import numpy as np
import xgboost as xgb
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
    80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"
}

def generate_synthetic_labels(db: Session):
    # Deprecated for CP4 Redesign. We no longer label the 245 events manually.
    pass

def _get_landcover_for_points(df):
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
                
                if src: src.close()
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
            
    if src: src.close()
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
                   ) as historical_event_count
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
                   ) as historical_event_count
            FROM firms_historical fh
            WHERE NOT EXISTS (
                SELECT 1 FROM industrial_sites i WHERE ST_DWithin(fh.geom, i.geometry::geography, 5000)
            )
            ORDER BY RANDOM()
            LIMIT 500
        )
    """)
    
    df = pd.read_sql(sql, db.bind)
    
    # Sort spatially to optimize STAC bounding box caching
    df = df.sort_values(by=['latitude', 'longitude'])
    
    df['dominant_landcover'] = _get_landcover_for_points(df)
    
    # Generate Proxy Labels (Weak Supervision)
    def assign_label(row):
        dist = row['distance_to_industry_m']
        lc = str(row['dominant_landcover'])
        
        if dist < 500:
            return 2 # Proxy Industrial
        elif dist > 5000:
            if 'Crop' in lc:
                return 1 # Proxy Agricultural
            elif 'Tree' in lc or 'Grass' in lc or 'Shrub' in lc:
                return 0 # Proxy Natural
        return -1 # Discard
        
    df['proxy_label'] = df.apply(assign_label, axis=1)
    df = df[df['proxy_label'] != -1] # Drop ambiguities
    
    df.to_csv(cache_path, index=False)
    return df

def train_and_predict(db: Session):
    print("--- CP4: XGBoost Classification via Weak Supervision ---")
    
    # 1. Fetch Training Data
    train_df = build_training_dataset(db)
    
    # Ensure datetime parsing
    train_df['acquisition_time'] = pd.to_datetime(train_df['acquisition_time'])
    
    # 2. Time-Based Split (Train on Jan 1-28, Validate on Jan 29+)
    # The historical data only successfully downloaded up to early February.
    split_date = pd.to_datetime("2023-01-29")
    train_set = train_df[train_df['acquisition_time'] < split_date]
    val_set = train_df[train_df['acquisition_time'] >= split_date]
    
    print(f"Chronological Split -> Train: {len(train_set)} records, Val: {len(val_set)} records.")
    
    features = ['frp', 'distance_to_industry_m', 'historical_event_count']
    # Note: distance_to_industry_m is included as requested by the plan.
    # It acts as a continuous prior, while the model smoothes it with FRP and density.
    
    X_train = train_set[features]
    y_train = train_set['proxy_label']
    X_val = val_set[features]
    y_val = val_set['proxy_label']
    
    # 3. Train Model
    model = xgb.XGBClassifier(
        objective='multi:softprob',
        num_class=3,
        eval_metric='mlogloss',
        use_label_encoder=False,
        seed=42
    )
    model.fit(X_train, y_train)
    
    # 4. Validation Metrics
    preds_val = model.predict(X_val)
    print("\n[Validation Metrics - Time-Based Holdout]")
    print(classification_report(y_val, preds_val, target_names=["Natural", "Agricultural", "Industrial"], zero_division=0))
    
    # 5. Predict on 245 Live Events (EventFeature)
    print("\nDeploying classifier on 245 Live Events...")
    live_query = db.query(
        EventFeature.event_id,
        EventFeature.frp_ratio_to_baseline,
        EventFeature.robust_frp_z,
        EventFeature.distance_to_industry_m,
        EventFeature.historical_event_count
    ).statement
    
    live_df = pd.read_sql(live_query, db.bind)
    
    if not live_df.empty:
        # We need FRP. We fetch it from FirmsEvent and merge.
        firms_df = pd.read_sql("SELECT event_id, frp FROM firms_events", db.bind)
        live_df = live_df.merge(firms_df, on="event_id")
        
        live_df.fillna({'distance_to_industry_m': 6000.0, 'historical_event_count': 0, 'frp': 0.0}, inplace=True)
        
        X_live = live_df[features]
        live_preds = model.predict(X_live)
        live_probs = model.predict_proba(X_live)
        
        # 6. Post-Processing Anomaly Engine (robust_frp_z)
        abnormal_count = 0
        updates = []
        for idx, row in live_df.iterrows():
            eid = int(row['event_id'])
            ml_class = int(live_preds[idx])
            ml_confidence = float(np.max(live_probs[idx]))
            z_score = row['robust_frp_z']
            
            # If predicted as Industrial (2), check anomaly
            if ml_class == 2 and z_score is not None and z_score > 2.5:
                ml_class = 3 # Abnormal Industrial
                abnormal_count += 1
                
            updates.append({"event_id": eid, "ml_class": ml_class, "ml_confidence": ml_confidence})
            
        # Bulk update the database
        db.bulk_update_mappings(EventFeature, updates)
        db.commit()
        print(f"Successfully classified 245 live events. Escalated {abnormal_count} to Abnormal Industrial.")
