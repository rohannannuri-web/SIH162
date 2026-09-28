import os
import requests
import pandas as pd
import io
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.firms import FirmsHistoricalEvent
from app.utils.config import settings

FIRMS_API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

def fetch_and_store_historical_firms_data(db: Session, bbox: str = "68.7,8.4,97.25,37.6", year: int = 2023):
    """
    Fetches 1 year of historical FIRMS data for a bounding box in 5-day chunks.
    This respects the NASA FIRMS historical API constraints.
    """
    api_key = settings.firms_api_key
    if not api_key or api_key == "your_nasa_firms_key_here":
        raise ValueError("Valid FIRMS_API_KEY is required to fetch historical data.")

    # Check if we already have data for this year to prevent duplicates during multiple runs
    # We'll just do a simple count check
    existing_count = db.query(FirmsHistoricalEvent).count()
    if existing_count > 0:
        print(f"firms_historical already contains {existing_count} records. Skipping historical ingestion.")
        return existing_count

    print(f"Starting 1-year historical fetch for {year}. This requires ~73 API calls (5-day chunks).")
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31)
    current_date = start_date
    
    total_added = 0
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        url = f"{FIRMS_API_BASE}/{api_key}/VIIRS_SNPP_SP/{bbox}/5/{date_str}"
        print(f"Fetching chunk starting at {date_str}...")
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
                
                events = []
                for _, row in df.iterrows():
                    # Parse date and time
                    try:
                        acq_date = row.get('acq_date')
                        acq_time = str(row.get('acq_time')).zfill(4)
                        acq_dt = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M")
                    except Exception:
                        continue
                        
                    lat = float(row['latitude'])
                    lon = float(row['longitude'])
                    frp = float(row.get('frp', 0.0))
                    if pd.isna(frp):
                        frp = 0.0
                        
                    geom_wkt = f"POINT({lon} {lat})"
                    
                    events.append({
                        "latitude": lat,
                        "longitude": lon,
                        "geom": geom_wkt,
                        "acquisition_time": acq_dt,
                        "frp": frp
                    })
                
                if events:
                    # Bulk insert mapping is much faster
                    db.bulk_insert_mappings(FirmsHistoricalEvent, events)
                    db.commit()
                    total_added += len(events)
                    
            else:
                print(f"Error for date {date_str}: {response.text}")
                
        except Exception as e:
            print(f"Failed to fetch chunk {date_str}: {e}")
            db.rollback()
            
        current_date += timedelta(days=5)
        
    print(f"Successfully ingested {total_added} historical records for {year}.")
    return total_added
