"""
init_db.py — Master orchestration script
=========================================
Runs the complete ETL + ML pipeline in order.

Phases added in this revision:
  --seed   : Insert static curated seed industrial sites (Phase 3a)
  --cluster: DBSCAN facility-complex clustering (Phase 3a)
  --all    : Runs all phases in dependency order
"""

from app.models.database import engine, Base
from app.models.firms import FirmsEvent, FirmsHistoricalEvent
from app.models.industrial import IndustrialSite
from app.models.features import EventFeature, IndustrialBaseline, FusedEventScore
from app.models.alert import Alert
from app.models.facility_cluster import FacilityComplex, FacilityHysteresisState
from app.services.atmospheric_service import AtmosphericReading, AtmosphericBaseline
from app.models.database import SessionLocal
from app.services.firms_ingestion import fetch_and_store_firms_data
from app.services.osm_service import fetch_and_store_osm_infrastructure
from app.services.landcover_service import enrich_firms_with_landcover
from app.services.enrichment_service import calculate_distance_to_industrial
from app.services.historical_service import generate_historical_baselines, calculate_event_features
from app.services.ml_service import generate_synthetic_labels, train_and_predict
from app.services.clustering_service import insert_seed_sites, cluster_industrial_sites
import sys


def init_db():
    print("Creating / verifying database tables (including PostGIS geometries)...")
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        print("Database schema verified successfully.")
    except Exception as e:
        print(f"Error creating database schema: {e}")
        sys.exit(1)


def ingest_sample_data():
    db = SessionLocal()
    try:
        print("Fetching NASA FIRMS data (VIIRS SNPP + NOAA-20 + MODIS)...")
        fetch_and_store_firms_data(db)
    except ValueError as ve:
        print(f"\n[SKIP] {ve}")
    except Exception as e:
        print(f"\n[ERROR] Ingestion failed: {e}")
    finally:
        db.close()


def ingest_osm_data():
    db = SessionLocal()
    try:
        print("Fetching OSM industrial infrastructure...")
        fetch_and_store_osm_infrastructure(db)
    except Exception as e:
        print(f"\n[ERROR] OSM ingestion failed: {e}")
    finally:
        db.close()


def seed_sites():
    db = SessionLocal()
    try:
        print("Inserting static curated seed industrial sites (Phase 3a)...")
        insert_seed_sites(db)
    except Exception as e:
        print(f"\n[ERROR] Seed insertion failed: {e}")
    finally:
        db.close()


def cluster_sites():
    db = SessionLocal()
    try:
        print("Running DBSCAN facility-complex clustering (Phase 3a)...")
        cluster_industrial_sites(db)
    except Exception as e:
        print(f"\n[ERROR] Clustering failed: {e}")
    finally:
        db.close()


def enrich_data():
    db = SessionLocal()
    try:
        print("Starting Data Enrichment Phase...")
        calculate_distance_to_industrial(db)
        enrich_firms_with_landcover(db)
    except Exception as e:
        print(f"\n[ERROR] Enrichment failed: {e}")
    finally:
        db.close()


from app.services.historical_ingestion import fetch_and_store_historical_firms_data


def generate_features():
    db = SessionLocal()
    try:
        print("Starting Historical Intelligence & Feature Generation Phase...")
        fetch_and_store_historical_firms_data(db, year=2023)
        generate_historical_baselines(db)
        calculate_event_features(db)
    except Exception as e:
        print(f"\n[ERROR] Feature generation failed: {e}")
    finally:
        db.close()


def run_ml():
    db = SessionLocal()
    try:
        print("Starting AI Classification Phase (with SHAP + circularity ablation)...")
        generate_synthetic_labels(db)
        train_and_predict(db)
    except Exception as e:
        print(f"\n[ERROR] ML phase failed: {e}")
    finally:
        db.close()


def run_validated_events():
    """Phase 4b — Run verified event validation set."""
    db = SessionLocal()
    try:
        from app.services.verified_events import run_verified_event_validation
        run_verified_event_validation(db)
    except Exception as e:
        print(f"\n[ERROR] Verified event validation failed: {e}")
    finally:
        db.close()


def run_atmospheric():
    db = SessionLocal()
    try:
        from app.services.atmospheric_service import analyze_atmospheric_anomaly
        from app.models.facility_cluster import FacilityComplex
        from datetime import date
        print("Starting Atmospheric Fusion Phase (S5P TROPOMI)...")
        complexes = db.query(FacilityComplex).all()
        today = date.today().isoformat()
        
        anom_count = 0
        for fc in complexes:
            report = analyze_atmospheric_anomaly(db, fc.complex_id, fc.centroid_lon, fc.centroid_lat, today)
            if report.get("any_anomalous"):
                anom_count += 1
        print(f"\n[Atmospheric] Analyzed {len(complexes)} complexes. Found {anom_count} with gas anomalies.")
    except Exception as e:
        print(f"\n[ERROR] Atmospheric phase failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--ingest":
            ingest_sample_data()
        elif arg == "--osm":
            ingest_osm_data()
        elif arg == "--seed":
            seed_sites()
        elif arg == "--cluster":
            cluster_sites()
        elif arg == "--enrich":
            enrich_data()
        elif arg == "--features":
            generate_features()
        elif arg == "--ml":
            run_ml()
        elif arg == "--validate":
            run_validated_events()
        elif arg == "--atmospheric":
            run_atmospheric()
        elif arg == "--all":
            ingest_sample_data()
            ingest_osm_data()
            seed_sites()       # Phase 3a: always-on seed layer
            cluster_sites()    # Phase 3a: DBSCAN clustering
            enrich_data()
            generate_features()
            run_ml()
            run_atmospheric()  # Phase 5: TROPOMI atmospheric fusion
            run_validated_events()  # Phase 4b: validated against real incidents
    else:
        print("\nInitialization complete.")
        print("Run with: --ingest | --osm | --seed | --cluster | --enrich | --features | --ml | --atmospheric | --validate | --all")
