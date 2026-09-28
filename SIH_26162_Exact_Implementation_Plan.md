# SIH 26162 — Exact Implementation Plan
## AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources

**Problem Statement ID:** 26162  
**Problem Statement:** AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data  
**Organization:** National Technical Research Organisation (NTRO)  
**Theme:** Disaster Management  
**Category:** Software  

---

# 1. Objective

Build an AI-enabled geospatial system that ingests satellite thermal-anomaly detections, adds spatial and environmental context, analyzes historical thermal behavior, and produces an explainable classification of each detected event.

The system must primarily distinguish:

1. Natural / forest fires
2. Agricultural burning
3. Persistent industrial thermal sources
4. Abnormal / suspected industrial thermal events
5. Mining / extraction-related thermal activity
6. Other non-vegetation / static thermal sources
7. Unknown / insufficient evidence

The final output must be displayed on a GIS dashboard with:

- Event location
- Event class
- Confidence score
- FRP and other FIRMS attributes
- Nearby industrial infrastructure
- Land-cover context
- Historical event behavior
- Evidence used for the classification
- Risk / abnormality level
- Optional satellite-image evidence for ambiguous events

---

# 2. Core Design Principle

## FIRMS is the trigger, not the final answer.

The system should not treat a FIRMS detection as proof that a fire is industrial or natural.

Instead:

```text
FIRMS Thermal Detection
        ↓
Spatial Context
        ↓
Temporal / Historical Behavior
        ↓
Feature Fusion
        ↓
Primary ML Classification
        ↓
Confidence Check
        ↓
If ambiguous → Satellite Image Analysis
        ↓
Final Classification + Evidence
        ↓
GIS Dashboard + Alert
```

The central differentiator is the ability to determine whether a thermal source is behaving normally or abnormally by combining:

- location,
- industrial context,
- land cover,
- historical frequency,
- FRP behavior,
- temporal patterns,
- optional satellite evidence.

---

# 3. Final Architecture

```text
                    ┌─────────────────────┐
                    │     NASA FIRMS     │
                    │ VIIRS / MODIS Data │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ FIRMS Data Ingestion│
                    │ Validation + Clean  │
                    └──────────┬──────────┘
                               │
                               ▼
                   ┌──────────────────────┐
                   │ Spatial Normalization│
                   │ Buffer / uncertainty │
                   └──────────┬───────────┘
                              │
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
 ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐
 │ OSM / Industry │  │ Land Cover     │  │ Historical FIRMS   │
 │ Infrastructure │  │ Context        │  │ Event History      │
 └───────┬────────┘  └───────┬────────┘  └──────────┬─────────┘
         │                   │                      │
         └───────────────────┼──────────────────────┘
                             ▼
                  ┌────────────────────────┐
                  │ Feature Engineering    │
                  │ Spatial + Temporal +   │
                  │ Thermal + Contextual   │
                  └───────────┬────────────┘
                              ▼
                  ┌────────────────────────┐
                  │ Site Baseline /        │
                  │ Anomaly Detection      │
                  └───────────┬────────────┘
                              ▼
                  ┌────────────────────────┐
                  │ Primary ML Classifier  │
                  │ XGBoost                 │
                  └───────────┬────────────┘
                              ▼
                     ┌─────────────────┐
                     │ Confidence Gate │
                     └───────┬─────────┘
                         High │ Low
                              │
             ┌────────────────┴─────────────────┐
             │                                  │
             ▼                                  ▼
     ┌─────────────────┐                ┌──────────────────┐
     │ Final Result    │                │ Sentinel-2 / -1  │
     │ + Evidence      │                │ Satellite Check  │
     └────────┬────────┘                └────────┬─────────┘
              │                                  │
              └────────────────┬─────────────────┘
                               ▼
                    ┌─────────────────────────┐
                    │ FastAPI Backend         │
                    │ GIS + Alert APIs        │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │ React / Next.js         │
                    │ Mapbox / Deck.gl        │
                    │ GIS Dashboard            │
                    └─────────────────────────┘
```

---

# 4. Technology Stack

## 4.1 Backend

| Layer | Technology |
|---|---|
| Main language | Python 3.11+ |
| API | FastAPI |
| Data processing | Pandas, NumPy |
| Geospatial processing | GeoPandas, Shapely, PyProj |
| ML | XGBoost, scikit-learn |
| Database | PostgreSQL |
| Spatial extension | PostGIS |
| Background jobs | APScheduler initially; Celery + Redis only if required |
| HTTP/API clients | requests / httpx |
| Validation | Pydantic |
| Logging | Python logging / structlog |

---

## 4.2 Frontend

| Layer | Technology |
|---|---|
| Framework | React.js or Next.js |
| Map | Mapbox GL JS |
| High-density rendering | Deck.gl if needed |
| Charts | Recharts / Apache ECharts |
| HTTP | Axios / fetch |
| UI | Tailwind CSS / component library |
| State | React Query + lightweight local state |

---

## 4.3 Data Sources

### Required

1. NASA FIRMS
2. OpenStreetMap / Overpass API
3. Land-cover dataset
4. Satellite imagery for ambiguous cases

### Recommended selection

- **Thermal trigger:** NASA FIRMS VIIRS
- **Historical thermal source:** NASA FIRMS archive / available historical products
- **Industrial context:** OpenStreetMap
- **Land cover:** Copernicus LCFM or ESA WorldCover
- **Optical confirmation:** Sentinel-2
- **SAR confirmation:** Sentinel-1

### Optional future layer

- INSAT / MOSDAC products for higher-frequency regional monitoring where access and licensing allow

---

# 5. Important Technical Rules

## 5.1 Never treat the FIRMS coordinate as an exact fire boundary

A FIRMS point represents a satellite detection associated with a pixel footprint.

Therefore do not use only:

```text
FIRMS point ∩ industrial polygon
```

as a hard classification rule.

Instead use:

```text
FIRMS detection
      ↓
spatial tolerance / buffer
      ↓
nearby facilities
      ↓
distance + facility type + land cover
      ↓
industrial-context score
```

---

## 5.2 Do not use hard land-cover rules

Do not implement:

```text
Forest → definitely natural
Industrial land → definitely industrial
Cropland → definitely agriculture
```

Instead use them as weighted features.

Example:

```text
forest_fraction
cropland_fraction
industrial_fraction
urban_fraction
distance_to_industry
```

---

## 5.3 Do not classify an accident only from a high FRP value

Use deviation from site-specific historical behavior.

```text
current FRP
      ↓
site historical baseline
      ↓
deviation score
      ↓
abnormality evidence
```

---

## 5.4 Do not claim Sentinel-2 gives real-time confirmation

Sentinel-2 should be considered:

- confirmatory,
- contextual,
- image-based evidence when a suitable observation is available.

It should not be presented as guaranteed immediate confirmation after every FIRMS event.

---

## 5.5 Do not use smoke color as a deterministic material classifier

Use visual information only as supporting evidence.

Possible features:

- plume presence
- plume direction
- plume length
- plume morphology
- burn scar
- spatial expansion
- spectral characteristics

Do not claim:

```text
black smoke = oil
white smoke = vegetation
```

as a hard rule.

---

# 6. End-to-End Processing Pipeline

## Step 1 — Ingest FIRMS Data

Create a scheduled ingestion job.

### Input

For each event, collect at minimum:

```text
latitude
longitude
acquisition datetime
satellite
brightness / thermal attributes available in the feed
FRP
confidence
scan
track
day/night flag where available
```

### Process

```text
FIRMS API / download
        ↓
validate fields
        ↓
remove malformed rows
        ↓
normalize datetime
        ↓
convert latitude/longitude
        ↓
create PostGIS POINT
        ↓
store in firms_events
```

### Recommended initial polling

Run every hour.

Do not depend on hourly polling for historical backfill; separate live ingestion from historical ingestion.

---

# 7. FIRMS Database Table

## `firms_events`

```sql
CREATE TABLE firms_events (
    event_id BIGSERIAL PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom GEOGRAPHY(Point, 4326) NOT NULL,
    acquisition_time TIMESTAMP NOT NULL,
    satellite VARCHAR(50),
    instrument VARCHAR(50),
    frp DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    brightness DOUBLE PRECISION,
    scan DOUBLE PRECISION,
    track DOUBLE PRECISION,
    day_night VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add indexes:

```sql
CREATE INDEX idx_firms_geom
ON firms_events
USING GIST (geom);

CREATE INDEX idx_firms_time
ON firms_events (acquisition_time);

CREATE INDEX idx_firms_satellite
ON firms_events (satellite);
```

---

# 8. Step 2 — Build Industrial Infrastructure Layer

Use Overpass API to collect OSM infrastructure.

## Target features

At minimum:

```text
landuse=industrial
industrial=refinery
industrial=steelmaking
industrial=chemical
industrial=depot
power=plant
power=generator
man_made=works
man_made=storage_tank
amenity / industrial facility tags where appropriate
quarry
mine
```

Do not assume every tag is available everywhere.

---

# 9. Industrial Sites Table

## `industrial_sites`

```sql
CREATE TABLE industrial_sites (
    site_id BIGSERIAL PRIMARY KEY,
    osm_id VARCHAR(100),
    name TEXT,
    facility_type VARCHAR(100),
    source VARCHAR(50),
    geometry GEOMETRY(Geometry, 4326),
    centroid GEOGRAPHY(Point, 4326),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add:

```sql
CREATE INDEX idx_industrial_geom
ON industrial_sites
USING GIST (geometry);
```

---

# 10. Industrial Proximity Analysis

For every FIRMS event calculate:

```text
nearest industrial facility
distance to nearest facility
facility type
number of industrial features within radius
industrial land fraction in local buffer
```

Suggested initial radii:

```text
250 m
500 m
1 km
2 km
```

Do not use all radii as final truth. Use them as features.

Example SQL pattern:

```sql
SELECT
    f.event_id,
    i.site_id,
    i.facility_type,
    ST_Distance(f.geom, i.centroid) AS distance_m
FROM firms_events f
JOIN industrial_sites i
ON ST_DWithin(f.geom, i.centroid, 2000);
```

---

# 11. Step 3 — Land-Cover Context

For each FIRMS event, retrieve land-cover composition around the event.

## Create local buffer

Example:

```text
250 m
500 m
1 km
```

Calculate:

```text
forest_fraction
cropland_fraction
grassland_fraction
builtup_fraction
bareland_fraction
water_fraction
industrial-context fraction if available
```

Store derived features rather than repeatedly querying raster data during classification.

---

# 12. Land-Cover Table

## `event_landcover`

```sql
CREATE TABLE event_landcover (
    event_id BIGINT REFERENCES firms_events(event_id),
    forest_fraction DOUBLE PRECISION,
    cropland_fraction DOUBLE PRECISION,
    grassland_fraction DOUBLE PRECISION,
    builtup_fraction DOUBLE PRECISION,
    bare_fraction DOUBLE PRECISION,
    water_fraction DOUBLE PRECISION,
    dominant_class VARCHAR(100),
    PRIMARY KEY (event_id)
);
```

---

# 13. Step 4 — Historical FIRMS Analysis

This is the most important intelligence layer.

For every event associated with an industrial site:

1. Identify the corresponding site.
2. Retrieve historical FIRMS detections around the site.
3. Build a site-specific thermal profile.
4. Compare the current event against the profile.

---

# 14. Site-Level Baseline

For each industrial site calculate:

```text
historical_event_count
events_per_day
events_per_week
events_per_month
mean_frp
median_frp
FRP standard deviation
FRP median absolute deviation
maximum observed FRP
typical FRP percentile range
typical detection time pattern
recent activity
days since previous detection
spatial spread of detections
```

Recommended historical window:

```text
At least 6–12 months for prototype
1–2 years when historical coverage permits
```

---

# 15. Temporal Features

For each event calculate:

```text
event_frequency
days_since_last_event
events_last_24h
events_last_7d
events_last_30d
events_last_90d
mean_frp_last_30d
median_frp_last_30d
max_frp_last_30d
current_frp / historical_median_frp
current_frp percentile
FRP deviation score
```

Additional useful features:

```text
hour_of_day
day_of_week
month
season
```

Only include time-of-day features when data quality supports them.

---

# 16. Thermal Abnormality Score

Use a robust baseline.

Initial prototype:

```text
baseline = historical median FRP
mad = median absolute deviation

robust_z =
(current_frp - baseline) / (1.4826 * mad + epsilon)
```

Then map to a bounded abnormality score.

Example concept:

```text
robust_z <= 1
    → normal range

1 < robust_z <= 2.5
    → moderately abnormal

robust_z > 2.5
    → strongly abnormal
```

These are starting thresholds for the prototype and should be tuned against validation data.

---

# 17. Spatial Abnormality

Track whether the present event is occurring outside the normal thermal footprint of the site.

Calculate:

```text
distance from historical event centroid
distance from historical 90% event boundary
current spatial extent
new hotspot detection
```

Example:

```text
Normal:
events repeatedly near flare stack

Current:
event appears 700 m away from historical hotspot
```

This should increase abnormality evidence.

---

# 18. Step 5 — Feature Engineering

Create one model-ready feature vector per event.

## Spatial features

```text
distance_to_nearest_industry
distance_to_refinery
distance_to_powerplant
distance_to_mine
distance_to_quarry
industrial_features_within_250m
industrial_features_within_500m
industrial_features_within_1km
industrial_land_fraction
```

## Land-cover features

```text
forest_fraction
cropland_fraction
grassland_fraction
builtup_fraction
bare_fraction
water_fraction
dominant_landcover
```

## Thermal features

```text
frp
brightness
confidence
scan
track
```

## Temporal features

```text
historical_event_count
events_last_7d
events_last_30d
events_last_90d
days_since_previous_event
historical_median_frp
historical_mean_frp
historical_max_frp
frp_ratio_to_baseline
robust_frp_z
historical_percentile
```

## Spatial-history features

```text
distance_from_historical_centroid
normal_footprint_flag
new_hotspot_flag
```

---

# 19. Feature Table

## `event_features`

```sql
CREATE TABLE event_features (
    event_id BIGINT PRIMARY KEY REFERENCES firms_events(event_id),

    distance_to_industry_m DOUBLE PRECISION,
    distance_to_refinery_m DOUBLE PRECISION,
    distance_to_powerplant_m DOUBLE PRECISION,
    distance_to_mine_m DOUBLE PRECISION,

    industrial_fraction DOUBLE PRECISION,
    forest_fraction DOUBLE PRECISION,
    cropland_fraction DOUBLE PRECISION,
    grassland_fraction DOUBLE PRECISION,
    builtup_fraction DOUBLE PRECISION,

    historical_event_count INTEGER,
    events_last_7d INTEGER,
    events_last_30d INTEGER,
    events_last_90d INTEGER,

    median_historical_frp DOUBLE PRECISION,
    mean_historical_frp DOUBLE PRECISION,
    max_historical_frp DOUBLE PRECISION,

    frp_ratio_to_baseline DOUBLE PRECISION,
    robust_frp_z DOUBLE PRECISION,

    days_since_previous_event DOUBLE PRECISION,
    distance_from_historical_centroid_m DOUBLE PRECISION,

    new_hotspot_flag BOOLEAN,
    normal_footprint_flag BOOLEAN
);
```

---

# 20. Step 6 — Primary ML Classifier

## Model

Use:

**XGBoost multiclass classifier**

Reasons:

- Works well with structured/tabular features.
- Handles nonlinear relationships.
- Works with mixed contextual features.
- Easier to explain than a large end-to-end image model.
- Suitable for a prototype with limited labeled data.

---

# 21. ML Classification Labels

Primary labels:

```text
0 = Natural / Forest Fire
1 = Agricultural Burning
2 = Persistent Industrial Thermal Source
3 = Abnormal Industrial Thermal Event
4 = Mining / Extraction Thermal Activity
5 = Other Non-Vegetation Thermal Source
6 = Unknown
```

The label set can be simplified for the first prototype to:

```text
Natural
Agricultural
Persistent Industrial
Abnormal Industrial
Unknown
```

and expanded after the base pipeline works.

---

# 22. Training Dataset Strategy

The biggest ML requirement is reliable labels.

Do not claim that raw FIRMS labels are ground truth.

Build a curated training/validation dataset from:

1. Historical FIRMS detections
2. Industrial infrastructure context
3. Land-cover context
4. Historical recurrence
5. Available satellite imagery
6. Manual review of selected events

For the prototype:

```text
Select representative geographic regions
        ↓
Collect historical FIRMS detections
        ↓
Join OSM infrastructure
        ↓
Join land cover
        ↓
Extract temporal features
        ↓
Manually validate a subset
        ↓
Create labeled dataset
        ↓
Train classifier
```

The manually verified subset should be kept as a higher-quality evaluation set.

---

# 23. Avoid Data Leakage

Do not randomly split events from the same industrial facility between train and test without checking geographic leakage.

Recommended evaluation design:

```text
Training facilities ≠ test facilities
```

or use a strict geographic hold-out region.

Also consider temporal hold-out:

```text
Older events → training
Newer events → validation/test
```

The goal is to determine whether the model learns general event behavior rather than memorizing a known location.

---

# 24. Model Output

The classifier should return:

```json
{
  "event_id": 12345,
  "predicted_class": "Abnormal Industrial Thermal Event",
  "confidence": 0.91,
  "class_probabilities": {
    "Natural": 0.02,
    "Agricultural": 0.01,
    "Persistent Industrial": 0.06,
    "Abnormal Industrial": 0.91
  }
}
```

---

# 25. Confidence Gate

Do not send every event to satellite-image analysis.

Example:

```text
confidence >= 0.80
    → accept primary classification

0.60 <= confidence < 0.80
    → review / supporting satellite analysis

confidence < 0.60
    → satellite analysis + mark uncertain
```

These are initial prototype thresholds.

They should be tuned using validation results.

---

# 26. Tier 3 — Satellite Analysis

Trigger satellite analysis when:

- classifier confidence is low,
- industrial and natural evidence are mixed,
- event lies near industrial/forest boundary,
- event is strongly abnormal,
- event is spatially new,
- operator requests additional evidence.

---

# 27. Sentinel-2 Pipeline

For a qualifying event:

```text
Event coordinates
      ↓
search available Sentinel-2 observations
      ↓
cloud filtering
      ↓
select best recent suitable image
      ↓
extract local patch
      ↓
preprocess bands
      ↓
generate visual/context features
      ↓
store image metadata
      ↓
attach evidence to event
```

Initial patch:

```text
5 km × 5 km
```

can be used for the prototype.

Do not require an image to exist for every event.

---

# 28. Sentinel-1 Pipeline

Use Sentinel-1 primarily for supporting evidence:

```text
event
 ↓
find suitable pre/post-event SAR observations
 ↓
extract patch
 ↓
compare structural/surface changes
 ↓
store change metrics
 ↓
add evidence to classifier
```

Potential uses:

- surface-change evidence
- structural-change evidence
- cloud-independent contextual imagery
- event-area comparison

Do not claim that Sentinel-1 automatically identifies every unregistered industrial plant.

---

# 29. Optional Computer Vision Module

Only add a CNN when a suitable labeled image dataset is available.

Potential architecture:

```text
EfficientNet / ResNet
```

Use it for supporting visual classification such as:

```text
plume present / absent
burn-scar evidence
industrial scene evidence
vegetation-fire evidence
```

Do not make the CNN the main classifier.

Primary classification remains feature-based and geospatial.

---

# 30. Evidence Fusion

Create a final evidence score.

Example:

```text
Industrial Context Score
Temporal Persistence Score
Thermal Abnormality Score
Land-Cover Score
Satellite Evidence Score
```

Then combine them using either:

### Option A — ML meta-classifier

or

### Option B — weighted scoring for the initial prototype

Example:

```text
industrial_context      0.25
temporal_behavior       0.20
thermal_abnormality     0.25
land_cover              0.10
satellite_evidence      0.20
```

These weights are starting values, not scientifically fixed values.

The final implementation should tune them against validation data.

---

# 31. Explainable Classification

Every result must include reasons.

Example:

```text
Classification:
ABNORMAL INDUSTRIAL THERMAL EVENT

Confidence:
91%

Supporting evidence:
✓ 150 m from refinery
✓ Historical thermal source detected frequently
✓ Current FRP = 3.4× site baseline
✓ Current hotspot lies outside historical hotspot center
✓ Surrounding land cover is predominantly industrial/built-up
✓ Supporting satellite observation available
```

This should be visible in the UI.

---

# 32. Classification Database Table

## `classifications`

```sql
CREATE TABLE classifications (
    classification_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT REFERENCES firms_events(event_id),

    predicted_class VARCHAR(100),
    confidence DOUBLE PRECISION,

    industrial_score DOUBLE PRECISION,
    persistence_score DOUBLE PRECISION,
    abnormality_score DOUBLE PRECISION,
    natural_score DOUBLE PRECISION,
    satellite_score DOUBLE PRECISION,

    explanation JSONB,
    model_version VARCHAR(50),

    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

# 33. Risk Levels

Use a separate operational risk level.

Example:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Risk should not be identical to class.

For example:

```text
Persistent Industrial Source
→ usually low operational risk

Abnormal Industrial Thermal Event
→ potentially high risk
```

Risk calculation should use:

```text
classification
+
confidence
+
thermal abnormality
+
recency
+
facility criticality
+
spatial context
```

---

# 34. Facility Criticality

Optional enhancement.

Assign facility categories:

```text
Tier A:
Refinery
Petrochemical complex
LNG terminal
Major thermal power plant

Tier B:
Steel
Mining
Chemical plant
Large industrial facility

Tier C:
Other industrial sources
```

Facility criticality can be used for alert prioritization.

Do not allow facility criticality alone to determine a fire classification.

---

# 35. FastAPI Backend Structure

Recommended project structure:

```text
backend/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── firms.py
│   │   ├── events.py
│   │   ├── classifications.py
│   │   ├── sites.py
│   │   ├── satellite.py
│   │   └── alerts.py
│   │
│   ├── services/
│   │   ├── firms_ingestion.py
│   │   ├── osm_service.py
│   │   ├── landcover_service.py
│   │   ├── historical_service.py
│   │   ├── feature_service.py
│   │   ├── anomaly_service.py
│   │   ├── classifier_service.py
│   │   ├── satellite_service.py
│   │   └── alert_service.py
│   │
│   ├── models/
│   │   ├── database.py
│   │   ├── firms.py
│   │   ├── industrial.py
│   │   └── classification.py
│   │
│   ├── schemas/
│   │   ├── event.py
│   │   ├── classification.py
│   │   └── site.py
│   │
│   └── utils/
│       ├── geo.py
│       ├── logging.py
│       └── config.py
│
├── ml/
│   ├── train.py
│   ├── predict.py
│   ├── features.py
│   └── model.pkl
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── samples/
│
├── tests/
└── requirements.txt
```

---

# 36. API Endpoints

## Event APIs

```http
GET /api/events
GET /api/events/{event_id}
GET /api/events/recent
GET /api/events/nearby
```

### Example filters

```text
class
confidence
risk
date_from
date_to
latitude
longitude
radius
facility_type
```

---

## Classification APIs

```http
GET /api/classifications
GET /api/classifications/{event_id}
POST /api/classifications/run/{event_id}
```

---

## Industrial site APIs

```http
GET /api/sites
GET /api/sites/{site_id}
GET /api/sites/nearby
```

---

## Historical APIs

```http
GET /api/events/{event_id}/history
GET /api/sites/{site_id}/thermal-profile
```

---

## Satellite APIs

```http
GET /api/satellite/{event_id}
POST /api/satellite/analyze/{event_id}
```

---

## Alert APIs

```http
GET /api/alerts
POST /api/alerts/test
```

---

# 37. GeoJSON API Output

Map endpoints should return GeoJSON.

Example:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [78.40, 17.45]
      },
      "properties": {
        "event_id": 12345,
        "class": "Abnormal Industrial Thermal Event",
        "confidence": 0.91,
        "risk": "HIGH",
        "frp": 130.4
      }
    }
  ]
}
```

This makes Mapbox integration straightforward.

---

# 38. Frontend Dashboard

## Main Layout

```text
┌────────────────────────────────────────────────────┐
│ SIH 26162 Thermal Intelligence Dashboard          │
├───────────────┬────────────────────────────────────┤
│ Filters       │                                    │
│               │                                    │
│ Date          │             GIS MAP                │
│ Class         │                                    │
│ Risk          │      FIRMS + Industrial +          │
│ Confidence    │      Land Cover overlays           │
│ Facility      │                                    │
│               │                                    │
├───────────────┴────────────────────────────────────┤
│ Selected Event:                                    │
│ Class | Confidence | FRP | Historical Behavior    │
│ Evidence | Risk | Satellite Evidence              │
└────────────────────────────────────────────────────┘
```

---

# 39. Map Layers

Implement toggles for:

```text
1. FIRMS raw detections
2. Classified events
3. Industrial sites
4. Industrial polygons
5. Land-cover layer
6. High-risk events
7. Historical event tracks
8. Satellite evidence footprints
```

---

# 40. Map Symbology

Recommended:

```text
RED    = Abnormal Industrial Thermal Event
ORANGE = Persistent Industrial Thermal Source
GREEN  = Natural / Forest Fire
YELLOW = Agricultural Burning
BLUE   = Other / Unknown
```

Use icon shape or outline in addition to color where possible for accessibility.

---

# 41. Event Details Panel

When the user clicks an event show:

```text
EVENT #12345

Classification:
Abnormal Industrial Thermal Event

Confidence:
91%

Risk:
HIGH

Coordinates:
17.XXXX, 78.XXXX

FRP:
130.4

Nearest Facility:
Refinery

Distance:
150 m

Historical Frequency:
High

Historical Median FRP:
38.2

Current / Baseline:
3.4×

Abnormality:
Strong

Land Cover:
Industrial / Built-up

Satellite:
Available

Evidence:
[expand]
```

---

# 42. Temporal Slider

Implement:

```text
Date range
────────●─────────────●──────
       start          end
```

The map should update events dynamically.

Useful views:

```text
Last 24 hours
Last 7 days
Last 30 days
Custom range
```

---

# 43. Historical Site View

Clicking an industrial facility should open:

```text
Facility Profile

Name
Type
Location

Historical Thermal Events
--------------------------------
Jan  → 12
Feb  → 15
Mar  → 13
Apr  → 14

Normal FRP Range:
35–55

Current:
132

Status:
ABNORMAL
```

This is a key demo feature.

---

# 44. Alert System

Trigger an alert when:

```text
abnormality_score > threshold
AND
confidence > threshold
```

Optional additional conditions:

```text
facility criticality high
event is recent
new hotspot detected
```

Alert channels:

- dashboard notification
- email
- SMS/mobile notification as optional future integration

Do not send an alert for every FIRMS point.

---

# 45. Alert Payload

Example:

```json
{
  "event_id": 12345,
  "title": "Suspected Abnormal Industrial Thermal Event",
  "facility": "Example Refinery",
  "classification": "Abnormal Industrial Thermal Event",
  "confidence": 0.91,
  "risk": "HIGH",
  "frp": 130.4,
  "baseline_frp": 38.2,
  "frp_ratio": 3.4,
  "latitude": 17.45,
  "longitude": 78.40,
  "timestamp": "2026-09-24T08:00:00Z"
}
```

---

# 46. Model Explainability

Use feature importance.

For XGBoost, display top contributing features such as:

```text
FRP deviation
distance to refinery
historical event frequency
industrial fraction
days since previous event
forest fraction
```

For a selected event:

```text
Top evidence:
1. FRP deviation
2. industrial proximity
3. historical persistence
4. new spatial hotspot
5. land-cover context
```

This makes the system easier to defend during evaluation.

---

# 47. Evaluation Plan

## Classification metrics

Report:

```text
Precision
Recall
F1-score
Macro F1
Confusion matrix
Per-class performance
```

Macro F1 is particularly important when some classes are much rarer than others.

---

## Operational metrics

Also report:

```text
Average processing time/event
Live ingestion delay
False-alert rate
High-risk alert precision
Spatial proximity error
Percentage of events resolved without satellite analysis
Percentage escalated to Tier 3
```

---

# 48. Most Important Evaluation Experiment

Compare three configurations.

### Baseline A

```text
FIRMS only
```

### Baseline B

```text
FIRMS + spatial + land cover
```

### Proposed

```text
FIRMS
+
OSM
+
land cover
+
historical behavior
+
thermal anomaly score
+
selective satellite analysis
```

Then show how classification quality and false-alert behavior change.

This is much more persuasive than showing only the final system.

---

# 49. Demo Scenario Design

Prepare exactly four showcase scenarios.

## Scenario 1 — Forest Fire

Expected flow:

```text
FIRMS
↓
forest context
↓
little/no industrial context
↓
historical behavior consistent with natural event
↓
Natural / Forest Fire
```

---

## Scenario 2 — Agricultural Burn

```text
FIRMS
↓
cropland context
↓
agricultural area
↓
seasonal / spatial evidence
↓
Agricultural Burning
```

---

## Scenario 3 — Persistent Industrial Source

```text
FIRMS
↓
industrial facility nearby
↓
frequent historical detections
↓
FRP inside normal range
↓
Persistent Industrial Thermal Source
```

---

## Scenario 4 — Abnormal Industrial Event

This is the primary showcase.

```text
FIRMS
↓
industrial facility
↓
historical persistence
↓
current FRP far above baseline
↓
new/spatially unusual hotspot
↓
satellite evidence if available
↓
High-confidence suspected abnormal industrial event
```

---

# 50. Main "Wow" Feature

The dashboard should not only say:

```text
Industrial Fire
```

It should say:

```text
SUSPECTED ABNORMAL INDUSTRIAL THERMAL EVENT

Confidence: 91%
Risk: HIGH

Why?
✓ Industrial facility nearby
✓ Persistent historical source
✓ Current FRP 3.4× historical baseline
✓ Spatial behavior differs from normal footprint
✓ Land-cover context supports industrial activity
✓ Supporting satellite image available
```

This is the feature the team should demonstrate to the jury.

---

# 51. Optional Plume Analysis

Add only as a supporting capability.

Possible pipeline:

```text
Satellite image
      ↓
Cloud filtering
      ↓
Plume candidate segmentation
      ↓
plume direction
plume length
plume area
      ↓
wind/context data
      ↓
downwind influence corridor
```

Output:

```text
Estimated plume direction
Estimated affected corridor
```

Do not claim automatic identification of the exact hazardous material unless validated data supports it.

---

# 52. Optional SAR-Based Missing Infrastructure Module

Future enhancement:

```text
Repeated unexplained thermal anomalies
        ↓
No industrial feature in OSM
        ↓
Check Sentinel-1 context
        ↓
Detect significant structural/surface features
        ↓
Flag "Potential unmapped industrial site"
        ↓
Human/authoritative verification
```

This should be presented as a **discovery/flagging mechanism**, not automatic proof of an unregistered industrial facility.

---

# 53. Optional INSAT Extension

Where data access permits:

```text
FIRMS
+
INSAT
+
Sentinel
```

Use INSAT for higher-frequency regional monitoring.

This can be placed in the future-work section rather than making the main prototype dependent on it.

---

# 54. Background Scheduler

For the first implementation, use APScheduler.

Jobs:

```text
Job 1:
Hourly FIRMS ingestion

Job 2:
Periodic historical synchronization

Job 3:
OSM infrastructure refresh

Job 4:
Land-cover cache update if required

Job 5:
Reclassification of unresolved events

Job 6:
Alert evaluation
```

Only add Celery + Redis when background workload requires parallel execution.

---

# 55. Processing Flow for One Event

Pseudo-flow:

```python
def process_event(event):

    validate_event(event)

    spatial_context = get_industrial_context(event)
    landcover_context = get_landcover_context(event)

    history = get_historical_behavior(
        event,
        spatial_context.nearest_site
    )

    features = build_features(
        event,
        spatial_context,
        landcover_context,
        history
    )

    anomaly = calculate_thermal_anomaly(features)

    prediction = classifier.predict(features)

    if prediction.confidence < CONFIDENCE_THRESHOLD:
        satellite = analyze_satellite_context(event)
        prediction = fuse_prediction(
            prediction,
            satellite,
            features
        )

    risk = calculate_risk(
        prediction,
        anomaly,
        spatial_context
    )

    explanation = build_explanation(
        prediction,
        anomaly,
        features
    )

    save_result(
        event,
        prediction,
        risk,
        explanation
    )

    trigger_alert_if_required(
        prediction,
        risk
    )
```

---

# 56. Core Service Responsibilities

## `firms_ingestion.py`

Responsible for:

```text
download
parse
validate
deduplicate
store
```

---

## `osm_service.py`

Responsible for:

```text
query Overpass
normalize tags
convert geometry
store infrastructure
```

---

## `landcover_service.py`

Responsible for:

```text
retrieve raster/context
calculate local land-cover fractions
cache results
```

---

## `historical_service.py`

Responsible for:

```text
retrieve event history
construct site baseline
calculate temporal statistics
```

---

## `anomaly_service.py`

Responsible for:

```text
FRP baseline
robust z-score
spatial abnormality
new hotspot detection
```

---

## `feature_service.py`

Responsible for:

```text
combine all raw/contextual information
produce ML feature vector
```

---

## `classifier_service.py`

Responsible for:

```text
model loading
prediction
confidence
feature importance
model versioning
```

---

## `satellite_service.py`

Responsible for:

```text
search Sentinel data
select image
download/extract patch
calculate evidence
```

---

## `alert_service.py`

Responsible for:

```text
risk threshold
alert creation
notifications
alert history
```

---

# 57. Duplicate Detection

A single fire may generate multiple detections.

Use a spatial-temporal clustering rule.

Initial approach:

```text
Group detections when:

distance <= X meters
AND
time difference <= Y hours
```

Example starting values:

```text
X = 500 m
Y = 6 hours
```

Tune based on observed FIRMS behavior.

Create:

## `fire_events`

A higher-level event cluster containing multiple FIRMS observations.

```sql
CREATE TABLE fire_events (
    fire_event_id BIGSERIAL PRIMARY KEY,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    centroid GEOGRAPHY(Point, 4326),
    detection_count INTEGER,
    max_frp DOUBLE PRECISION,
    classification VARCHAR(100),
    confidence DOUBLE PRECISION,
    risk VARCHAR(20)
);
```

This is preferable to treating every satellite observation as an entirely independent event.

---

# 58. Event Lifecycle

```text
DETECTED
   ↓
CONTEXT ENRICHED
   ↓
FEATURES GENERATED
   ↓
CLASSIFIED
   ↓
CONFIDENCE CHECK
   ↓
SATELLITE REVIEW if needed
   ↓
FINALIZED
   ↓
ALERTED if required
   ↓
MONITORED for future observations
```

---

# 59. Model Versioning

Store:

```text
model_name
model_version
training_date
feature_schema_version
```

Every classification must record the model version.

Example:

```text
xgb-industrial-v1.0
```

---

# 60. Configuration

Do not hard-code thresholds throughout the source code.

Create:

```text
config.yaml
```

Example:

```yaml
confidence:
  accept: 0.80
  review: 0.60

spatial:
  proximity_radii_m:
    - 250
    - 500
    - 1000
    - 2000

historical:
  baseline_days: 365

anomaly:
  moderate_z: 1.0
  strong_z: 2.5

alert:
  minimum_confidence: 0.80
  minimum_risk: HIGH
```

All thresholds must be configurable and tunable.

---

# 61. Security and Reliability

Implement:

```text
environment variables for API keys
no hard-coded credentials
request timeout
API retry with backoff
input validation
database transactions
structured logging
exception handling
rate-limit awareness
```

External service failures should not stop the complete pipeline.

Example:

```text
OSM unavailable
→ classify using other available features

Sentinel unavailable
→ keep primary classification
→ mark satellite evidence unavailable
```

---

# 62. Caching Strategy

Cache:

```text
OSM infrastructure
land-cover lookups
satellite search results
historical site statistics
```

This reduces external API calls and improves response time.

---

# 63. Docker Deployment

Recommended services:

```text
postgres-postgis
backend
frontend
```

Optional:

```text
redis
worker
```

Do not introduce Redis/worker services until required.

---

# 64. Docker Compose Structure

```text
docker-compose.yml

services:

  db:
    postgres + postgis

  backend:
    FastAPI

  frontend:
    React / Next.js
```

Optional:

```text
redis:
worker:
```

---

# 65. Environment Variables

Example:

```text
DATABASE_URL=
FIRMS_API_KEY=
OSM_OVERPASS_URL=
MAPBOX_TOKEN=
SENTINEL_CREDENTIALS=
EMAIL_API_KEY=
```

Never commit these values to Git.

---

# 66. Testing Strategy

## Unit tests

Test:

```text
FIRMS parsing
coordinate validation
distance calculations
feature engineering
baseline calculation
anomaly calculation
classification output
risk calculation
```

## Integration tests

Test:

```text
FIRMS → database
database → features
features → model
model → API
API → frontend
```

## End-to-end test

Use one known sample event and verify:

```text
ingestion
→ enrichment
→ classification
→ dashboard display
```

---

# 67. Performance Targets for Prototype

Use these as engineering targets rather than claimed final performance:

```text
API response for cached event:
< 1 second

Event classification without satellite retrieval:
a few seconds or less

Dashboard rendering:
smooth for thousands of points using server-side filtering / clustering

Satellite analysis:
asynchronous where download/processing is slow
```

Measure actual performance during implementation.

---

# 68. MVP Scope

The MVP must include:

```text
✓ FIRMS ingestion
✓ PostGIS database
✓ OSM industrial context
✓ Land-cover context
✓ Historical FIRMS analysis
✓ Site thermal baseline
✓ Feature engineering
✓ XGBoost classifier
✓ Confidence score
✓ Explainable evidence
✓ GIS dashboard
✓ Temporal filtering
✓ Event details panel
```

---

# 69. Phase 2 Scope

Add:

```text
✓ Sentinel-2 evidence
✓ Sentinel-1 evidence
✓ satellite-image metadata
✓ ambiguous-event review
✓ improved anomaly detection
✓ alerts
✓ facility criticality
```

---

# 70. Phase 3 Scope

Optional:

```text
✓ plume analysis
✓ wind/direction analysis
✓ SAR-based infrastructure discovery
✓ INSAT integration
✓ mobile notifications
✓ advanced deep-learning visual classifier
```

---

# 71. Recommended Implementation Order

## Phase 1 — Database + FIRMS

1. Install PostgreSQL + PostGIS.
2. Create tables.
3. Implement FIRMS ingestion.
4. Insert sample historical events.
5. Verify map coordinates.
6. Implement indexes.

---

## Phase 2 — Industrial Context

1. Query Overpass.
2. Normalize OSM tags.
3. Store facilities.
4. Implement distance queries.
5. Generate industrial-context features.

---

## Phase 3 — Land Cover

1. Select land-cover source.
2. Download/cache required tiles.
3. Build event-buffer statistics.
4. Store land-cover features.

---

## Phase 4 — Historical Intelligence

1. Link events to industrial sites.
2. Retrieve historical detections.
3. Construct site baselines.
4. Calculate FRP statistics.
5. Implement temporal features.
6. Implement anomaly score.
7. Implement spatial abnormality.

---

## Phase 5 — ML

1. Build curated labeled dataset.
2. Clean labels.
3. Prevent data leakage.
4. Split train/validation/test.
5. Train XGBoost.
6. Evaluate.
7. Tune thresholds.
8. Save model.
9. Implement prediction service.

---

## Phase 6 — Backend API

1. Create FastAPI project.
2. Create event endpoints.
3. Create classification endpoints.
4. Create site endpoints.
5. Create history endpoints.
6. Create GeoJSON endpoints.
7. Add error handling.
8. Add API documentation.

---

## Phase 7 — Dashboard

1. Create map.
2. Add FIRMS layer.
3. Add industrial layer.
4. Add classified layers.
5. Add filters.
6. Add event panel.
7. Add temporal slider.
8. Add history charts.
9. Add evidence panel.

---

## Phase 8 — Satellite Layer

1. Implement Sentinel search.
2. Add cloud filtering.
3. Extract event patch.
4. Add image viewer.
5. Add satellite evidence features.
6. Trigger only for ambiguous/high-priority cases.

---

## Phase 9 — Alerts

1. Define alert threshold.
2. Implement alert table.
3. Create dashboard alerts.
4. Add email/SMS as optional extension.
5. Test false-alert behavior.

---

## Phase 10 — Final Evaluation

Run the four demo scenarios.

Collect:

```text
classification metrics
false-alert metrics
processing time
tier distribution
number of events resolved without Tier 3
```

Prepare screenshots and charts.

---

# 72. Suggested Database Relationship

```text
firms_events
     │
     ├──────── event_landcover
     │
     ├──────── event_features
     │
     ├──────── classifications
     │
     └──────── fire_events
                  │
                  └──── alerts

industrial_sites
     │
     └──── historical thermal profile
```

---

# 73. Suggested Final UI Pages

## Page 1 — Live Dashboard

Purpose:

```text
Current thermal situation
```

Contains:

- map
- active events
- filters
- risk summary

---

## Page 2 — Event Investigation

Purpose:

```text
Investigate one thermal event
```

Contains:

- event location
- nearby industry
- historical graph
- FRP baseline
- classification
- confidence
- evidence
- satellite images

---

## Page 3 — Facility Monitoring

Purpose:

```text
Monitor one industrial site
```

Contains:

- thermal history
- normal baseline
- recent deviations
- event count
- current status

---

## Page 4 — Alerts

Purpose:

```text
Review abnormal events
```

Contains:

- alert status
- severity
- location
- timestamp
- confidence
- evidence

---

# 74. Example Facility Monitoring Logic

For each facility:

```python
def evaluate_facility(site_id):

    history = load_history(site_id)

    baseline = build_baseline(history)

    recent_events = get_recent_events(site_id)

    for event in recent_events:

        anomaly_score = calculate_anomaly(
            event.frp,
            baseline
        )

        spatial_score = calculate_spatial_change(
            event.location,
            history
        )

        classification = classify_event(
            event,
            anomaly_score,
            spatial_score
        )

        save_classification(classification)
```

---

# 75. Final Classification Logic

Conceptually:

```text
                 ┌─────────────────────────┐
                 │ FIRMS Thermal Detection │
                 └────────────┬────────────┘
                              ↓
                     Spatial Context
                              ↓
                    ┌─────────┴─────────┐
                    │                   │
             Strong natural       Strong industrial
             context              context
                    │                   │
                    ↓                   ↓
             Natural / Agri       Historical Profile
                                        ↓
                               ┌────────┴────────┐
                               │                 │
                         Normal behavior    Abnormal behavior
                               │                 │
                               ↓                 ↓
                        Persistent source   Suspected abnormal
                                            industrial event
```

This should remain a logical explanation, while the actual classification should be generated by the trained model plus supporting rules/evidence.

---

# 76. What NOT to Claim in the SIH Presentation

Do not claim:

```text
❌ 100% accurate classification
❌ FIRMS point is exact fire location
❌ OSM is complete ground truth
❌ every Sentinel-2 image is real-time
❌ smoke color proves material being burned
❌ high FRP automatically means explosion
❌ SAR automatically discovers hidden factories
❌ PostGIS alone guarantees 90% filtering
❌ satellite data gives guaranteed confirmation of every event
```

Instead use:

```text
✓ confidence-based classification
✓ contextual evidence fusion
✓ anomaly detection
✓ selective satellite verification
✓ explainable evidence
✓ uncertainty-aware output
```

---

# 77. Final Innovation Statement

Use the following technical positioning:

> The proposed system does not merely detect thermal anomalies. It creates a contextual thermal profile for each location by combining FIRMS observations, industrial infrastructure, land cover and historical behavior. Each new anomaly is compared against the expected behavior of its surrounding environment and industrial site. High-confidence events are classified directly, while ambiguous or abnormal events are selectively escalated to satellite-image analysis. The final result is an explainable classification with confidence, risk and supporting evidence.

---

# 78. Final System Summary

```text
NASA FIRMS
    ↓
Thermal Event Detection
    ↓
Spatial Context
(OSM + buffers + proximity)
    ↓
Land-Cover Context
(Copernicus / WorldCover)
    ↓
Historical Thermal Profile
(Frequency + FRP baseline + temporal behavior)
    ↓
Feature Fusion
    ↓
Thermal Anomaly Detection
    ↓
XGBoost Classification
    ↓
Confidence Gate
    ↓
Ambiguous? ── Yes → Sentinel-2 / Sentinel-1
    │
    No
    │
    └──────────────────────┐
                           ↓
                Explainable Final Result
                           ↓
                  Risk Assessment
                           ↓
                     GIS Dashboard
                           ↓
                       Alerting
```

---

# 79. Final MVP Definition

A successful SIH prototype should be able to take:

```text
one FIRMS thermal detection
```

and automatically produce:

```text
WHERE?
→ coordinates + nearby infrastructure

WHAT IS AROUND IT?
→ land cover + industrial context

HOW HAS THIS LOCATION BEHAVED?
→ historical thermal profile

IS CURRENT BEHAVIOR NORMAL?
→ baseline + anomaly score

WHAT IS THE MOST LIKELY CLASS?
→ ML classification

HOW CERTAIN ARE WE?
→ confidence score

WHY DID THE SYSTEM DECIDE THIS?
→ evidence panel

DO WE NEED MORE EVIDENCE?
→ selective Sentinel analysis

WHAT SHOULD THE OPERATOR SEE?
→ GIS event + risk + explanation
```

That is the complete implementation target for SIH 26162.
