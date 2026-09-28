import planetary_computer
from pystac_client import Client
import rasterio
from pyproj import Transformer
from sqlalchemy.orm import Session
from app.models.firms import FirmsEvent

# ESA WorldCover classes
ESA_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen"
}

def enrich_firms_with_landcover(db: Session):
    """
    Queries Planetary Computer STAC for ESA WorldCover (2021) to enrich FIRMS points.
    """
    events = db.query(FirmsEvent).filter(FirmsEvent.land_cover_class == None).all()
    if not events:
        print("All FIRMS events already have land cover data.")
        return 0

    print(f"Fetching Land Cover data for {len(events)} events...")
    
    # Initialize STAC client
    try:
        client = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace
        )
    except Exception as e:
        print(f"Failed to connect to Planetary Computer: {e}")
        return 0

    enriched = 0
    # Process each point. A highly optimized version would group points by STAC item bounds.
    # We will do it simple first: look up each point (caching the last opened rasterio dataset if it matches bounds)
    last_item_id = None
    src = None
    transformer = None

    for event in events:
        try:
            # Check if current src covers the point
            if src and src.bounds.left <= event.longitude <= src.bounds.right and src.bounds.bottom <= event.latitude <= src.bounds.top:
                pass # Still within the same tile
            else:
                # Search for new tile
                search = client.search(
                    collections=["esa-worldcover"],
                    intersects={"type": "Point", "coordinates": [event.longitude, event.latitude]},
                    datetime="2021-01-01/2021-12-31"
                )
                items = list(search.items())
                if not items:
                    print(f"No ESA WorldCover tile found for event {event.event_id}")
                    event.land_cover_class = "Unknown"
                    continue
                
                item = items[0]
                
                # We need to open the new COG
                if src:
                    src.close()
                
                cog_href = item.assets["map"].href
                src = rasterio.open(cog_href)
                transformer = Transformer.from_crs("epsg:4326", src.crs, always_xy=True)

            # Sample pixel
            x, y = transformer.transform(event.longitude, event.latitude)
            val = list(src.sample([(x, y)]))
            class_val = val[0][0]
            
            land_cover_str = ESA_CLASSES.get(class_val, f"Unknown ({class_val})")
            event.land_cover_class = land_cover_str
            enriched += 1

        except Exception as e:
            print(f"Failed to process land cover for event {event.event_id}: {e}")
            event.land_cover_class = "Error"
    
    if src:
        src.close()

    db.commit()
    print(f"Successfully enriched {enriched} FIRMS events with Land Cover data.")
    return enriched
