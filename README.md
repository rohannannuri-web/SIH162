# SIH 26162 - AI-Based Detection and Classification of Industrial Fires

This project provides an AI-enabled geospatial system that ingests satellite thermal anomaly detections (NASA FIRMS), enriches them with spatial and environmental context (OpenStreetMap, Land Cover), analyzes historical thermal behavior, and produces explainable classifications of each detected event using Machine Learning (XGBoost) and Microsoft Planetary Computer STAC (Sentinel-2) capabilities.

## Features

- **NASA FIRMS Ingestion**: Pulls thermal anomaly data automatically.
- **Contextual Enrichment**: Matches events with local OpenStreetMap (OSM) industrial infrastructure and land cover (ESA WorldCover).
- **Historical Analysis**: Calculates historical FRP baselines for specific locations to detect deviations.
- **ML Classification**: Uses an XGBoost model (via Weak Supervision) to classify events as Natural, Agricultural, or Industrial.
- **Alert System**: Triggers high-risk alerts based on Z-score abnormality and actual ML confidence metrics.
- **Satellite Evidence**: Dynamically queries STAC APIs to fetch corresponding Sentinel-2 satellite imagery for visual confirmation.
- **Interactive Dashboard**: A React + Leaflet interface providing interactive filtering, alerting, and deep evidence evaluation.

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **PostgreSQL 14+** with **PostGIS** extension
- **NASA FIRMS API Key** (Get one at [FIRMS](https://firms.modaps.eosdis.nasa.gov/api/))

---

## 1. Database Setup

1. Install PostgreSQL and PostGIS.
2. Open `psql` or pgAdmin and create the database and user:
   ```sql
   CREATE DATABASE sih_db;
   CREATE USER sih_user WITH ENCRYPTED PASSWORD 'sih_password';
   GRANT ALL PRIVILEGES ON DATABASE sih_db TO sih_user;
   ```
3. Connect to `sih_db` and enable the PostGIS extension:
   ```sql
   \c sih_db
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

---

## 2. Backend Setup

The backend uses FastAPI, SQLAlchemy, and XGBoost.

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   
   # Windows
   .\venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the `backend` directory with your database URL and FIRMS API key:
   ```env
   DATABASE_URL=postgresql://sih_user:sih_password@localhost:5432/sih_db
   FIRMS_API_KEY=your_firms_api_key_here
   ```
5. Initialize the database and run the complete data ingestion/ML pipeline:
   ```bash
   python init_db.py --all
   ```
   *(This step will create tables, ingest NASA FIRMS data, fetch OSM infrastructure, enrich land-cover data, generate features, and run the ML classifier).*
6. Start the FastAPI server:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
7. To generate alerts, run the alert evaluation endpoint in a new terminal/PowerShell window:
   ```powershell
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/alerts/evaluate
   ```

---

## 3. Frontend Setup

The frontend uses React, Vite, Tailwind CSS, and Leaflet.

1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install Node.js dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
4. Open your browser and navigate to `http://localhost:5173`.

---

## Architecture Flow

1. **Ingestion**: Raw thermal data is pulled from NASA FIRMS.
2. **Spatial Processing**: PostGIS matches detections against OSM infrastructure polygons and ESA Land Cover geometries.
3. **Temporal Processing**: Compares real-time FRP against the historical median of that specific spatial buffer.
4. **ML Inference**: `ml_service.py` runs XGBoost inference to predict the source type (Natural vs. Ag vs. Industrial).
5. **Abnormality Filter**: Industrial events displaying massive FRP deviations (`robust_frp_z > 2.5`) and high model confidence are escalated to **Abnormal**.
6. **Delivery**: FastAPI serves the results, STAC dynamically provides Satellite previews, and React renders the interactive mapping.
