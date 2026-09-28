import pandas as pd
import requests
import io
from sqlalchemy.orm import Session
from app.models.firms import FirmsEvent
from app.utils.config import settings
from datetime import datetime

# Base URL for FIRMS API (using area instead of country for better API key compatibility)
FIRMS_API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

def fetch_and_store_firms_data(db: Session, source: str = "VIIRS_SNPP_NRT", bbox: str = "68.7,8.4,97.25,37.6", days: int = 3):
    """
    Fetches real FIRMS data from NASA API for a bounding box (default: India) and stores it in the database.
    """
    api_key = settings.firms_api_key
    if not api_key or api_key == "your_nasa_firms_key_here":
        raise ValueError("Valid FIRMS_API_KEY is required to fetch real data.")
        
    url = f"{FIRMS_API_BASE}/{api_key}/{source}/{bbox}/{days}"
    print(f"Fetching FIRMS data from: {url.replace(api_key, 'HIDDEN_KEY')}")
    
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch data from FIRMS API: {response.text}")
        
    csv_data = response.content.decode('utf-8')
    df = pd.read_csv(io.StringIO(csv_data))
    
    print(f"Fetched {len(df)} records. Inserting into database...")
    
    events_added = 0
    duplicates_skipped = 0
    invalid_skipped = 0
    
    for _, row in df.iterrows():
        # Validate coordinates
        if pd.isna(row.get('latitude')) or pd.isna(row.get('longitude')):
            invalid_skipped += 1
            continue
            
        latitude = float(row['latitude'])
        longitude = float(row['longitude'])
        
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            invalid_skipped += 1
            continue

        # Parsing acq_date and acq_time
        acq_date = row.get('acq_date')
        acq_time = str(row.get('acq_time')).zfill(4)
        
        try:
            acquisition_time = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M")
        except Exception as e:
            print(f"Error parsing date {acq_date} {acq_time}: {e}")
            invalid_skipped += 1
            continue

        # Keep confidence as original string representation
        confidence = str(row.get('confidence', ''))
        
        frp = float(row.get('frp', 0.0))
        if pd.isna(frp):
            frp = 0.0

        # Check for duplicates based on lat, lon, and time
        existing_event = db.query(FirmsEvent).filter(
            FirmsEvent.latitude == latitude,
            FirmsEvent.longitude == longitude,
            FirmsEvent.acquisition_time == acquisition_time,
            FirmsEvent.satellite == str(row.get('satellite', source))
        ).first()
        
        if existing_event:
            duplicates_skipped += 1
            continue

        point_geom = f"POINT({longitude} {latitude})"

        event = FirmsEvent(
            latitude=latitude,
            longitude=longitude,
            geom=point_geom,
            acquisition_time=acquisition_time,
            satellite=str(row.get('satellite', source)),
            instrument=str(row.get('instrument', source.split('_')[0])),
            frp=frp,
            confidence=confidence,
            brightness=float(row.get('bright_ti4', row.get('brightness', 0.0))),
            scan=float(row.get('scan', 0.0)),
            track=float(row.get('track', 0.0)),
            day_night=str(row.get('daynight', ''))
        )
        db.add(event)
        events_added += 1

    db.commit()
    print(f"Successfully added {events_added} FIRMS events. Skipped {duplicates_skipped} duplicates and {invalid_skipped} invalid records.")
    return events_added
