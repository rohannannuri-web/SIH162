from app.models.database import engine, Base
from app.models.firms import FirmsEvent # Must import all models to register them
from app.models.industrial import IndustrialSite
from app.models.database import SessionLocal
from app.services.firms_ingestion import fetch_and_store_firms_data
from app.services.osm_service import fetch_and_store_osm_infrastructure
from app.services.landcover_service import enrich_firms_with_landcover
from app.services.enrichment_service import calculate_distance_to_industrial
from app.services.historical_service import generate_historical_baselines, calculate_event_features
from app.services.ml_service import generate_synthetic_labels, train_and_predict
import sys

def init_db():
    print("Creating database tables (including PostGIS geometries)...")
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
        
        # Base.metadata.drop_all(bind=engine) # Keep commented to preserve data
        Base.metadata.create_all(bind=engine)
        print("Database schema verified successfully.")
    except Exception as e:
        print(f"Error creating database schema: {e}")
        sys.exit(1)

def ingest_sample_data():
    db = SessionLocal()
    try:
        print("Attempting to fetch and store NASA FIRMS data...")
        fetch_and_store_firms_data(db)
    except ValueError as ve:
        print(f"\n[SKIP INGESTION] {ve}")
        print("Please configure FIRMS_API_KEY in backend/.env")
    except Exception as e:
        print(f"\n[ERROR] Failed during ingestion: {e}")
    finally:
        db.close()

def ingest_osm_data():
    db = SessionLocal()
    try:
        print("Attempting to fetch and store OSM Industrial data...")
        fetch_and_store_osm_infrastructure(db)
    except Exception as e:
        print(f"\n[ERROR] Failed during OSM ingestion: {e}")
    finally:
        db.close()

def enrich_data():
    db = SessionLocal()
    try:
        print("Starting Data Enrichment Phase...")
        calculate_distance_to_industrial(db)
        enrich_firms_with_landcover(db)
    except Exception as e:
        print(f"\n[ERROR] Failed during enrichment: {e}")
    finally:
        db.close()

from app.services.historical_ingestion import fetch_and_store_historical_firms_data

def generate_features():
    db = SessionLocal()
    try:
        print("Starting Historical Intelligence & Feature Generation Phase...")
        
        # 1. Fetch genuine historical data
        fetch_and_store_historical_firms_data(db, year=2023)
        
        # 2. Build baselines from genuine data
        generate_historical_baselines(db)
        
        # 3. Build ML features
        calculate_event_features(db)
    except Exception as e:
        print(f"\n[ERROR] Failed during feature generation: {e}")
    finally:
        db.close()

def run_ml():
    db = SessionLocal()
    try:
        print("Starting AI Classification Phase...")
        generate_synthetic_labels(db)
        train_and_predict(db)
    except Exception as e:
        print(f"\n[ERROR] Failed during ML phase: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--ingest":
            ingest_sample_data()
        elif sys.argv[1] == "--osm":
            ingest_osm_data()
        elif sys.argv[1] == "--enrich":
            enrich_data()
        elif sys.argv[1] == "--features":
            generate_features()
        elif sys.argv[1] == "--ml":
            run_ml()
        elif sys.argv[1] == "--all":
            ingest_sample_data()
            ingest_osm_data()
            enrich_data()
            generate_features()
            run_ml()
    else:
        print("\nInitialization complete. Run `python init_db.py --ingest`, `--osm`, `--enrich`, `--features`, or `--ml`.")
