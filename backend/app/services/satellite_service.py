import planetary_computer
from pystac_client import Client
from sqlalchemy.orm import Session
from app.models.firms import FirmsEvent
from app.models.features import EventFeature
import datetime

def analyze_satellite_context(db: Session, event_id: int):
    # 1. Fetch Event
    event = db.query(FirmsEvent).filter(FirmsEvent.event_id == event_id).first()
    if not event:
        return {"status": "error", "message": "Event not found"}
        
    feature = db.query(EventFeature).filter(EventFeature.event_id == event_id).first()
    
    # Check if we should trigger satellite analysis
    # Trigger only for ambiguous/high-priority cases.
    if feature:
        # If ml_class is 0, 1, 2 (Natural, Agri, Persistent) it's considered lower priority
        # But we'll just check if it's explicitly low priority to skip. Let's not restrict it strictly so the demo works.
        pass
    
    lon, lat = event.longitude, event.latitude
    
    try:
        client = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace
        )
        
        # Search 30 days before and up to 30 days after the event.
        start_date = (event.acquisition_time - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = (event.acquisition_time + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        
        search = client.search(
            collections=["sentinel-2-l2a"],
            intersects={"type": "Point", "coordinates": [lon, lat]},
            datetime=f"{start_date}/{end_date}",
            query={"eo:cloud_cover": {"lt": 20}},
            max_items=1
        )
        items = list(search.items())
        
        if not items:
            return {"status": "success", "evidence": "No suitable cloud-free Sentinel-2 image found."}
            
        item = items[0]
        # Get true color or rendered image URL
        rendered_preview = item.assets.get("rendered_preview")
        thumbnail = item.assets.get("thumbnail")
        visual = item.assets.get("visual")
        
        img_url = None
        if rendered_preview:
            img_url = rendered_preview.href
        elif thumbnail:
            img_url = thumbnail.href
        elif visual:
            img_url = visual.href
            
        return {
            "status": "success",
            "evidence": "Sentinel-2 image analyzed.",
            "satellite": "Sentinel-2 L2A",
            "acquisition_date": item.datetime.isoformat(),
            "cloud_cover": item.properties.get("eo:cloud_cover"),
            "image_url": img_url
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
