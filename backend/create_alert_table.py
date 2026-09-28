from app.models.database import engine, Base
from app.models.firms import FirmsEvent
from app.models.features import EventFeature
from app.models.alert import Alert

print("Creating alerts table...")
Base.metadata.create_all(bind=engine)
print("Done.")
