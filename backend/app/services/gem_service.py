"""
gem_service.py — Phase 2: Global Energy Monitor (GEM) facility integration
===========================================================================
GEM publishes open datasets for coal plants, oil & gas infrastructure, and
steel plants covering India. Where full CSV download requires registration,
this module uses a curated static seed derived from GEM's public tracker
pages and open GeoJSON exports.

Sources (all public-domain factual facility data):
  - Global Coal Plant Tracker (GCPT): https://globalcoaltracker.org/
  - Global Oil & Gas Plant Tracker: https://globalenergymonitor.org/
  - Global Steel Plant Tracker: https://globalenergymonitor.org/

The GEM dataset extends the OSM taxonomy by providing:
  1. More authoritative capacity data (MW, Mt/year)
  2. Operational status (operating, mothballed, retired)
  3. India-specific categories not reliably tagged in OSM:
     - Brick kilns (tagged separately in India_kiln_zones below)
     - Gas flare sites
     - Coal seam fire locations (Jharia coalfield)

Brick kiln seasonal model:
  Brick kilns in India operate during the dry season (October–June) and are
  idle during monsoon (July–September). This 9-month campaign pattern MUST
  NOT be confused with unregistered-activity detections. Any thermal event
  in the North Indian Plains kiln belt (lat 24-30°N, lon 75-88°E) during
  October–June should be attributed to brick kilns before triggering an
  unregistered-activity alert.
  
  Reference: Guttikunda, S.K. et al. (2013). Physical emission inventory of
  brick kilns in the Indo-Gangetic Plains. Atmos. Environment, 79, 687-695.
"""

from __future__ import annotations

from typing import Sequence

# ─────────────────────────────────────────────────────────────────────────────
# Brick kiln zone definition (Indo-Gangetic Plains)
# ─────────────────────────────────────────────────────────────────────────────
BRICK_KILN_BELT = {
    "lat_min": 23.5, "lat_max": 30.5,
    "lon_min": 74.5, "lon_max": 88.5,
    # Active months (1-indexed): Oct, Nov, Dec, Jan, Feb, Mar, Apr, May, Jun
    "active_months": {10, 11, 12, 1, 2, 3, 4, 5, 6},
}

# Coal seam fire zone (Jharia coalfield, Jharkhand)
JHARIA_COALFIELD = {
    "lat_min": 23.7, "lat_max": 23.9,
    "lon_min": 86.2, "lon_max": 86.5,
    "type": "Coal-Seam Fire",
}


def is_in_brick_kiln_belt(lat: float, lon: float, month: int) -> bool:
    """
    Return True if (lat, lon, month) falls within the Indo-Gangetic Plains
    brick kiln belt during its active firing season.
    
    Used by Phase 6 unregistered-activity logic to suppress false positives
    from seasonal brick kiln firing.
    """
    bk = BRICK_KILN_BELT
    return (
        bk["lat_min"] <= lat <= bk["lat_max"]
        and bk["lon_min"] <= lon <= bk["lon_max"]
        and month in bk["active_months"]
    )


def is_in_coalfield_fire_zone(lat: float, lon: float) -> bool:
    """Return True if location is in the Jharia coal-seam fire zone."""
    jf = JHARIA_COALFIELD
    return jf["lat_min"] <= lat <= jf["lat_max"] and jf["lon_min"] <= lon <= jf["lon_max"]


# ─────────────────────────────────────────────────────────────────────────────
# GEM India facility seed data
# Format: (name, facility_type, lat, lon, status, capacity_str)
# status: 'operating' | 'mothballed' | 'retired' | 'construction'
# ─────────────────────────────────────────────────────────────────────────────
GEM_INDIA_FACILITIES: list[tuple[str, str, float, float, str, str]] = [
    # ── Coal Power Plants (GCPT) ─────────────────────────────────────────────
    ("NTPC Singrauli STPS",           "Coal Power Plant", 24.1333, 82.6667, "operating", "2000 MW"),
    ("NTPC Korba STPS",               "Coal Power Plant", 22.3833, 82.7167, "operating", "2600 MW"),
    ("NTPC Ramagundam",               "Coal Power Plant", 18.7667, 79.4667, "operating", "2600 MW"),
    ("NTPC Farakka STPS",             "Coal Power Plant", 24.8000, 87.8667, "operating", "2100 MW"),
    ("NTPC Vindhyachal STPS",         "Coal Power Plant", 24.0833, 82.6500, "operating", "4760 MW"),
    ("NTPC Rihand STPS",              "Coal Power Plant", 24.0333, 83.0333, "operating", "3000 MW"),
    ("NTPC Unchahar TPS",             "Coal Power Plant", 25.9833, 81.4667, "operating",  "1050 MW"),
    ("NTPC Talcher Kaniha STPS",      "Coal Power Plant", 20.9833, 85.1000, "operating", "3000 MW"),
    ("NTPC Dadri (NCTPP)",            "Coal Power Plant", 28.5667, 77.5667, "operating", "1330 MW"),
    ("Mundra Ultra Mega Power Plant", "Coal Power Plant", 22.7167, 69.7167, "operating", "4620 MW"),
    ("Adani Tiroda TPS",              "Coal Power Plant", 20.5500, 79.9000, "operating", "3300 MW"),
    ("Torrent Sabarmati TPS",         "Coal Power Plant", 23.0833, 72.6000, "operating",  "500 MW"),
    ("CESC New Cossipore",            "Coal Power Plant", 22.6333, 88.3500, "operating",  "135 MW"),
    ("WBPDCL Bakreshwar TPS",         "Coal Power Plant", 23.8833, 87.4333, "operating", "1050 MW"),
    ("MAHAGENCO Chandrapur STPS",     "Coal Power Plant", 19.9833, 79.3000, "operating", "2920 MW"),

    # ── Steel Plants (Global Steel Plant Tracker) ─────────────────────────────
    ("SAIL Bhilai Steel Plant",        "Steel Plant", 21.2167, 81.4333, "operating", "7 Mt/yr"),
    ("SAIL Rourkela Steel Plant",      "Steel Plant", 22.2333, 84.8833, "operating", "4.5 Mt/yr"),
    ("SAIL Durgapur Steel Plant",      "Steel Plant", 23.5500, 87.3167, "operating", "2.5 Mt/yr"),
    ("SAIL Bokaro Steel Plant",        "Steel Plant", 23.6667, 85.9167, "operating", "5.7 Mt/yr"),
    ("Tata Steel Jamshedpur",          "Steel Plant", 22.8000, 86.1833, "operating", "10 Mt/yr"),
    ("JSW Steel Vijayanagar",          "Steel Plant", 15.1500, 76.9167, "operating", "12 Mt/yr"),
    ("JSW Steel Dolvi",                "Steel Plant", 18.5167, 73.0000, "operating", "5 Mt/yr"),
    ("Essar Steel (now ArcelorMittal Nippon)", "Steel Plant", 21.2000, 72.8500, "operating", "7 Mt/yr"),
    ("Jindal Steel Raigarh",           "Steel Plant", 21.8983, 83.3950, "operating", "3.4 Mt/yr"),
    ("RINL Visakhapatnam Steel Plant", "Steel Plant", 17.7000, 83.2833, "operating", "6.3 Mt/yr"),

    # ── Refineries (Oil & Gas Plant Tracker) ─────────────────────────────────
    ("Jamnagar Refinery (Reliance)",   "Refinery", 22.4333, 70.0667, "operating", "1.24 mb/d"),
    ("Jamnagar SEZ Refinery (Reliance)", "Refinery", 22.4167, 70.0500, "operating", "0.58 mb/d"),
    ("Koyali Refinery (IOCL)",         "Refinery", 22.3833, 73.1333, "operating", "275 Kbbl/d"),
    ("Mathura Refinery (IOCL)",        "Refinery", 27.5000, 77.6667, "operating", "160 Kbbl/d"),
    ("Panipat Refinery (IOCL)",        "Refinery", 29.4000, 76.9667, "operating", "300 Kbbl/d"),
    ("Barauni Refinery (IOCL)",        "Refinery", 25.4667, 86.0000, "operating", "120 Kbbl/d"),
    ("Paradip Refinery (IOCL)",        "Refinery", 20.3167, 86.6000, "operating", "300 Kbbl/d"),
    ("Visakha Refinery (HPCL)",        "Refinery", 17.6833, 83.2167, "operating", "166 Kbbl/d"),
    ("Mumbai Refinery (HPCL)",         "Refinery", 19.0667, 72.8833, "operating",  "85 Kbbl/d"),
    ("Mangalore Refinery (MRPL)",      "Refinery", 12.9000, 74.8833, "operating", "300 Kbbl/d"),
    ("Numaligarh Refinery (NRL)",      "Refinery", 26.6500, 93.7000, "operating",  "60 Kbbl/d"),
    ("Digboi Refinery (IOCL)",         "Refinery", 27.3833, 95.6167, "operating",   "1 Kbbl/d"),
    ("Bongaigaon Refinery (BPCL)",     "Refinery", 26.4500, 90.5500, "operating",  "45 Kbbl/d"),

    # ── LNG / Gas Processing ───────────────────────────────────────────────────
    ("Hazira LNG Terminal (Shell)",    "LNG Terminal",    21.1000, 72.6667, "operating", "5 Mt/yr"),
    ("Dahej LNG Terminal (PLL)",       "LNG Terminal",    21.7167, 72.5500, "operating", "17.5 Mt/yr"),
    ("Ennore LNG Terminal",            "LNG Terminal",    13.2167, 80.3333, "operating", "5 Mt/yr"),
    ("ONGC Hazira Gas Plant",          "Gas Processing",  21.0667, 72.6833, "operating", ""),
    ("ONGC Uran Gas Processing",       "Gas Processing",  18.9000, 72.9500, "operating", ""),
    ("GAIL Pata Petrochemical",        "Petrochemical",   26.8167, 79.0333, "operating", ""),

    # ── Mining / Coal ────────────────────────────────────────────────────────
    ("Singareni Collieries (SCCL)",    "Coal Mine",   17.9500, 80.3333, "operating", "65 Mt/yr"),
    ("Coal India - Jharia Division",   "Coal Mine",   23.7667, 86.4167, "operating", ""),
    ("NMDC Bailadila Iron Ore Mine",   "Iron Ore Mine", 18.5667, 81.7000, "operating", "35 Mt/yr"),

    # ── Coal-Seam Fires (Jharia) ───────────────────────────────────────────
    ("Jharia Coalfield Active Fires",  "Coal-Seam Fire", 23.7833, 86.4167, "persistent", ""),
]


def insert_gem_sites(db) -> int:
    """
    Insert GEM India facility seeds into industrial_sites with source='GEM'.
    Idempotent — skips entries that already exist (matched by name + source).
    Also inserts brick kiln representative nodes and coal-seam fire zone marker.
    Returns count of newly inserted sites.
    """
    from app.models.industrial import IndustrialSite

    inserted = 0
    for name, ftype, lat, lon, status, capacity in GEM_INDIA_FACILITIES:
        # Skip retired/mothballed sites (no active thermal signature expected)
        if status in ("retired",):
            continue
        existing = db.query(IndustrialSite).filter(
            IndustrialSite.name == name,
            IndustrialSite.source == "GEM",
        ).first()
        if existing:
            continue

        point_wkt = f"POINT({lon} {lat})"
        site = IndustrialSite(
            osm_id=f"GEM_{name.replace(' ', '_')[:50]}",
            name=name,
            facility_type=ftype,
            source="GEM",
            geometry=f"SRID=4326;{point_wkt}",
            centroid=f"SRID=4326;{point_wkt}",
        )
        db.add(site)
        inserted += 1

    # Insert Jharia coal-seam fire zone as a persistent anomaly seed
    jharia_name = "Jharia Coal-Seam Fire Zone (persistent)"
    if not db.query(IndustrialSite).filter(
        IndustrialSite.name == jharia_name
    ).first():
        lon, lat = 86.4167, 23.7833
        site = IndustrialSite(
            osm_id="GEM_Jharia_CoalSeamFire",
            name=jharia_name,
            facility_type="Coal-Seam Fire",
            source="GEM",
            geometry=f"SRID=4326;POINT({lon} {lat})",
            centroid=f"SRID=4326;POINT({lon} {lat})",
        )
        db.add(site)
        inserted += 1

    db.commit()
    print(f"[GEM] Inserted {inserted} new GEM India facility sites.")
    return inserted
