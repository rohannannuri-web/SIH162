import requests
from sqlalchemy.orm import Session
from app.models.industrial import IndustrialSite
from app.models.firms import FirmsEvent
from shapely.geometry import shape, Point, Polygon
import json

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

def fetch_and_store_osm_infrastructure(db: Session, radius_m: int = 2000):
    """
    Fetches OSM industrial infrastructure around all current FIRMS events in the database.
    This prevents downloading the entire country's industrial zones.
    """
    # 1. Get all FIRMS events
    # To prevent Overpass timeouts during mass testing, we sample 20 events.
    # In production, this would be run incrementally on new incoming events only.
    events = db.query(FirmsEvent).limit(20).all()
    if not events:
        print("No FIRMS events found to center OSM queries. Run FIRMS ingestion first.")
        return 0

    print(f"Generating Overpass query for {len(events)} sample locations (to avoid timeouts)...")
    
    # 2. Build Overpass Query using a tiny bounding box instead of 'around' (which is expensive)
    tags = [
        '"landuse"="industrial"',
        '"power"="plant"',
        '"man_made"="works"',
        '"man_made"="kiln"',
        '"industrial"="refinery"',
        '"industrial"="steel"',
        '"industrial"="metal"',
        '"industrial"="cement"',
        '"industrial"="gas"',
        '"industrial"="chemical"',
        '"landuse"="quarry"',
        '"man_made"="petroleum_well"',
        '"man_made"="gas_well"',
        '"man_made"="flare"',
    ]
    
    query_parts = []
    for event in events:
        # +/- 0.02 degrees is ~2km
        min_lat, max_lat = event.latitude - 0.02, event.latitude + 0.02
        min_lon, max_lon = event.longitude - 0.02, event.longitude + 0.02
        bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        
        for tag in tags:
            query_parts.append(f'nwr[{tag}]({bbox});')

    # To avoid URL too long, we might need to batch them if there are thousands.
    # But 245 events * 8 tags = ~1960 lines. Overpass can handle large POST requests.
    
    import time
    batch_size = 80 # 10 events per batch to avoid complexity limits
    total_added = 0
    
    headers = {
        'User-Agent': 'SIH162-Fire-Classification-App/1.0'
    }

    for i in range(0, len(query_parts), batch_size):
        batch = query_parts[i:i + batch_size]
        query = f"[out:json][timeout:90];\n(\n  " + "\n  ".join(batch) + "\n);\nout geom;"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(OVERPASS_URL, data={'data': query}, headers=headers)
                response.raise_for_status()
                data = response.json()
                break
            except Exception as e:
                print(f"Overpass API error on batch {i}, attempt {attempt + 1}: {e}")
                time.sleep(5)
        else:
            print(f"Failed to fetch batch {i} after {max_retries} attempts. Skipping.")
            continue
        
        time.sleep(2) # rate limiting delay

        elements = data.get("elements", [])
        print(f"Fetched {len(elements)} OSM elements in batch...")
        
        for el in elements:
            el_id = f"{el['type']}/{el['id']}"
            
            # Skip if already exists
            exists = db.query(IndustrialSite).filter(IndustrialSite.osm_id == el_id).first()
            if exists:
                continue

            tags = el.get("tags", {})
            name = tags.get("name", "Unnamed Facility")
            
            # Determine facility type based on tags — expanded taxonomy (Phase 2)
            facility_type = "Industrial"
            man_made = tags.get("man_made", "")
            industrial = tags.get("industrial", "")
            power_tag = tags.get("power", "")
            landuse = tags.get("landuse", "")

            if man_made == "kiln":
                facility_type = "Brick Kiln"     # seasonal: Oct-Jun (see gem_service)
            elif power_tag in ("plant", "generator"):
                facility_type = "Power Plant"
            elif industrial == "refinery":
                facility_type = "Refinery"
            elif industrial in ("steel", "steelmaking", "metal", "metalworks"):
                facility_type = "Steel Plant"
            elif industrial == "cement":
                facility_type = "Cement Plant"
            elif industrial in ("gas", "gas_processing", "lng"):
                facility_type = "Gas Processing"
            elif industrial in ("chemical", "petrochemical"):
                facility_type = "Petrochemical"
            elif industrial == "mine" or landuse == "quarry":
                facility_type = "Mining"
            elif man_made in ("petroleum_well", "gas_well"):
                facility_type = "Oil/Gas Well"
            elif man_made == "flare":
                facility_type = "Gas Flare"
            elif man_made == "storage_tank":
                facility_type = "Storage Tank"
            elif man_made == "works" and industrial:
                facility_type = f"Industrial ({industrial})"

            # Parse Geometry
            geom = None
            centroid = None
            if el['type'] == 'node':
                geom = Point(el['lon'], el['lat'])
                centroid = geom
            else:
                # way or relation with geometry
                # Overpass out geom returns 'geometry' list of dicts with lat/lon for ways
                # For relations it's complex, we'll try to extract what we can
                coords = []
                if 'geometry' in el:
                    coords = [(pt['lon'], pt['lat']) for pt in el['geometry']]
                elif 'bounds' in el:
                    # Approximation for relations without full geom reconstructed
                    b = el['bounds']
                    coords = [
                        (b['minlon'], b['minlat']),
                        (b['maxlon'], b['minlat']),
                        (b['maxlon'], b['maxlat']),
                        (b['minlon'], b['maxlat']),
                        (b['minlon'], b['minlat'])
                    ]
                
                if len(coords) >= 3:
                    try:
                        geom = Polygon(coords)
                        centroid = geom.centroid
                    except:
                        pass
                elif len(coords) > 0:
                    geom = Point(coords[0])
                    centroid = geom

            if geom and centroid:
                site = IndustrialSite(
                    osm_id=el_id,
                    name=name,
                    facility_type=facility_type,
                    source="OSM",
                    geometry=f"SRID=4326;{geom.wkt}",
                    centroid=f"SRID=4326;{centroid.wkt}"
                )
                db.add(site)
                total_added += 1

        db.commit()

    print(f"Successfully added {total_added} OSM industrial sites to the database.")
    return total_added
