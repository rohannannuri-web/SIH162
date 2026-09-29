from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import events, sites, classifications, historical, satellite, alerts, complexes, atmospheric

app = FastAPI(
    title="SIH 26162 - Thermal Intelligence API",
    description="API for accessing FIRMS thermal anomalies, industrial sites, classification results, and historical baselines.",
    version="1.0.0"
)

# Configure CORS for the frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(sites.router, prefix="/api/sites", tags=["Industrial Sites"])
app.include_router(classifications.router, prefix="/api/classifications", tags=["Classifications"])
app.include_router(historical.router, prefix="/api/historical", tags=["Historical Data"])
app.include_router(satellite.router, prefix="/api/satellite", tags=["Satellite"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(complexes.router, prefix="/api/complexes", tags=["Facility Complexes"])
app.include_router(atmospheric.router, prefix="/api/atmospheric", tags=["Atmospheric"])


@app.get("/")
def read_root():
    return {"message": "Welcome to the SIH 26162 Thermal Intelligence API"}
