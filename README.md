# 🔥 HELIOS-X: Satellite-Powered Thermal Intelligence

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.100.0-009688.svg)](https://fastapi.tiangolo.com/) [![React](https://img.shields.io/badge/React-18.x-61DAFB.svg)](https://reactjs.org/) [![PostGIS](https://img.shields.io/badge/PostGIS-15.x-336791.svg)](https://postgis.net/)

**HELIOS-X** is an advanced, production-grade geospatial intelligence system designed to automatically detect, classify, and verify industrial thermal anomalies from space. By fusing multi-spectral satellite imagery, atmospheric gas concentrations, and machine learning, HELIOS-X acts as a global watchdog for unregistered industrial activity and catastrophic high-risk events.

---

## 🌟 Key Features

### 1. 🛰️ Multi-Constellation Ingestion
HELIOS-X continuously ingests near real-time thermal anomalies (FRP, brightness, and geospatial coordinates) from NASA's FIRMS API using **VIIRS (SNPP/NOAA-20)** and **MODIS** sensors.

### 2. 🤖 ML-Driven Event Classification (XGBoost + SHAP)
The core engine filters out routine agricultural and forest fires, isolating purely industrial events.
- **Dynamic Hysteresis:** Tracks the historical baseline of known industrial facilities.
- **Explainable AI:** Uses SHAP TreeExplainer to provide human-readable evidence traces detailing *why* an event was flagged.

### 3. 🌫️ Atmospheric Gas Cross-Verification (Sentinel-5P)
Automatically cross-references thermal spikes with anomalous local concentrations of NO₂, SO₂, and CO using the **Tropomi** instrument on Sentinel-5P, guaranteeing multi-modal confirmation for emissions violations.

### 4. 📸 Burn Scar & Disturbance Validation (Sentinel-2 & Sentinel-1)
Queries the Microsoft Planetary Computer STAC API to analyze pre- and post-event satellite imagery.
- **Optical (Sentinel-2):** Computes Normalized Burn Ratio (ΔNBR) to confirm ground disturbance.
- **SAR (Sentinel-1):** Automatically falls back to Synthetic Aperture Radar (SAR) backscatter analysis if cloud cover exceeds 30%.

### 5. 🚨 4-Channel Unregistered Activity Alerting
HELIOS-X generates a highly confident **Fused Event Score** by combining:
1. Thermal Confidence
2. Atmospheric Trace Gases
3. Ground Disturbance (Burn Scar)
4. Nighttime Activity (Day/Night proxy)

If a high-confidence thermal/gas event occurs further than 3km from any registered facility (and sits outside known seasonal anomalies like the Indo-Gangetic Brick Kiln belt), it automatically triggers an **UNREGISTERED ACTIVITY** dispatch alert.

---

## 🛠️ Tech Stack

### Backend Engine
- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Database:** PostgreSQL + PostGIS (Dockerized)
- **ORM:** SQLAlchemy + GeoAlchemy2
- **Machine Learning:** XGBoost, SHAP, scikit-learn
- **Geospatial Processing:** Rasterio, Xarray, Pyproj, Shapely, PySTAC-Client

### Frontend Dashboard
- **Framework:** React 18 (Vite)
- **Styling:** TailwindCSS + Lucide Icons
- **Mapping:** React-Leaflet + OpenStreetMap
- **Charts:** Recharts

---

## 🚀 Quickstart Guide

### Prerequisites
1. **Docker Desktop** (must be running to boot the PostGIS database)
2. **Node.js 18+**
3. **Python 3.10+** (Conda/Miniconda recommended)

### 1. First-Time Setup (For Fresh Clones)
If you just cloned this repository, you need to install dependencies and set up your environment variables.

**Backend Setup:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```
*(Open the newly created `backend/.env` file and paste your NASA FIRMS API key)*

**Frontend Setup:**
```bash
cd ../frontend
npm install
cd ..
```

### 2. Launch the System
Ensure Docker Desktop is open. Simply execute the start script from the root directory:
```bash
./start.bat
```
This script will automatically:
1. Boot up the PostGIS database in Docker.
2. Start the FastAPI backend on `http://127.0.0.1:8000`.
3. Start the React frontend on `http://localhost:5173`.

### 3. Initialize the Intelligence Pipeline
In a new terminal window, navigate to the `backend` directory and run the full pipeline to ingest real-time data, fetch satellite imagery, and compute fusion scores:

```bash
cd backend
python init_db.py --all
```
*(Note: Initial run may take 3-5 minutes as it queries NASA FIRMS, OpenStreetMap, and Microsoft Planetary Computer).*

### 4. Access the Dashboard
Open your web browser and navigate to **[http://localhost:5173](http://localhost:5173)** to view the live HELIOS-X dashboard.

---

## 📁 System Architecture

```text
HELIOS-X/
│
├── backend/                  # Python FastAPI Backend Engine
│   ├── app/
│   │   ├── api/              # RESTful API Endpoints (Fusion, Alerts, Events)
│   │   ├── models/           # SQLAlchemy DB Schemas & PostGIS Structs
│   │   └── services/         # Core Logic (ML, SHAP, Satellite I/O, Fusion)
│   └── init_db.py            # Master CLI Pipeline Orchestrator
│
├── frontend/                 # React UI Dashboard
│   ├── src/
│   │   ├── components/       # Glassmorphic UI Panels, Map, Charts
│   │   └── App.jsx           # Main Dashboard View & Layer Control
│   └── tailwind.config.js    # Custom Theme Configuration
│
├── docker-compose.yml        # PostgreSQL/PostGIS Configuration
└── start.bat                 # 1-Click Launch Script
```

---

## 🛡️ License & Acknowledgements

Developed for SIH 2026. Satellite data provided courtesy of NASA FIRMS, ESA Copernicus, OpenStreetMap, and the Microsoft Planetary Computer.
