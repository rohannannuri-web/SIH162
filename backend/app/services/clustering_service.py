"""
clustering_service.py — Phase 3a: Facility-complex clustering + seed layer
===========================================================================
Two responsibilities:
  1. STATIC SEED LAYER: Always-present curated dataset of ~20 major Indian
     industrial complexes. Merged in unconditionally beneath the DBSCAN output
     so demo-critical sites are always covered regardless of Overpass
     reliability.

  2. DBSCAN CLUSTERING: Clusters all industrial_sites (OSM + seed) into
     facility_complex entities at CLUSTER_RADIUS_KM (default 3km). Each
     cluster's centroid becomes the anchor for persistence keying and
     atmospheric fusion in later phases.

The seed layer is inserted into industrial_sites with source='SEED' so the
rest of the pipeline (PostGIS distance queries, baseline computation, etc.)
treats them identically to OSM-sourced sites.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.industrial import IndustrialSite
from app.models.facility_cluster import FacilityComplex, FacilityHysteresisState, CLUSTER_RADIUS_KM

# ---------------------------------------------------------------------------
# Static seed layer: ~20 major Indian industrial complexes
# Format: (name, facility_type, latitude, longitude)
# ---------------------------------------------------------------------------
SEED_INDUSTRIAL_SITES: list[tuple[str, str, float, float]] = [
    # Refineries
    ("Jamnagar Refinery (Reliance)", "Refinery",          22.4333, 70.0667),
    ("Koyali Refinery (IOCL)",       "Refinery",          22.3833, 73.1333),
    ("Mathura Refinery (IOCL)",      "Refinery",          27.5000, 77.6667),
    ("Barauni Refinery (IOCL)",      "Refinery",          25.4667, 86.0000),
    ("Paradip Refinery (IOCL)",      "Refinery",          20.3167, 86.6000),
    ("Visakha Refinery (HPCL)",      "Refinery",          17.6833, 83.2167),
    # Thermal Power Plants
    ("NTPC Singrauli STPS",          "Power Plant",       24.1333, 82.6667),
    ("NTPC Vindhyachal STPS",        "Power Plant",       24.0833, 82.6500),
    ("NTPC Ramagundam",              "Power Plant",       18.8000, 79.4667),
    ("NTPC Rihand STPS",             "Power Plant",       24.0000, 83.0000),
    ("Mundra Ultra Mega Power Plant","Power Plant",       22.7167, 69.7167),
    # Steel Plants
    ("SAIL Bhilai Steel Plant",      "Steel Plant",       21.2167, 81.4333),
    ("SAIL Rourkela Steel Plant",    "Steel Plant",       22.2333, 84.8833),
    ("JSW Steel Vijayanagar",        "Steel Plant",       15.1500, 76.9167),
    ("Tata Steel Jamshedpur",        "Steel Plant",       22.8000, 86.1833),
    # LNG / Gas / Petrochemical
    ("Hazira LNG Terminal (Shell)",  "LNG Terminal",      21.1000, 72.6667),
    ("Dahej Petrochemical Complex",  "Petrochemical",     21.7167, 72.5500),
    ("ONGC Hazira Gas Plant",        "Gas Processing",    21.0667, 72.6833),
    # Mining / Cement
    ("Singareni Collieries (SCCL)",  "Coal Mine",         17.9500, 80.3333),
    ("ACC Cement Wadi Plant",        "Cement",            17.0500, 76.9667),
]


def insert_seed_sites(db: Session) -> int:
    """
    Insert the curated seed layer into industrial_sites with source='SEED'.
    Idempotent — skips entries that already exist (matched by name).
    """
    inserted = 0
    for name, ftype, lat, lon in SEED_INDUSTRIAL_SITES:
        existing = db.query(IndustrialSite).filter(
            IndustrialSite.name == name,
            IndustrialSite.source == "SEED",
        ).first()
        if existing:
            continue
        point_wkt = f"POINT({lon} {lat})"
        site = IndustrialSite(
            osm_id=f"SEED_{name.replace(' ', '_')[:40]}",
            name=name,
            facility_type=ftype,
            source="SEED",
            geometry=f"SRID=4326;{point_wkt}",
            centroid=f"SRID=4326;{point_wkt}",
        )
        db.add(site)
        inserted += 1
    db.commit()
    print(f"[Seed Layer] Inserted {inserted} new seed industrial sites.")
    return inserted


# ---------------------------------------------------------------------------
# DBSCAN clustering
# ---------------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0


def _haversine_matrix_rad(lats_deg: np.ndarray, lons_deg: np.ndarray) -> np.ndarray:
    """Precompute lat/lon in radians for haversine DBSCAN."""
    return np.column_stack([np.radians(lats_deg), np.radians(lons_deg)])


def cluster_industrial_sites(db: Session) -> int:
    """
    Cluster all industrial_sites centroids into facility_complexes using DBSCAN.
    Existing complex records are cleared and rebuilt on each call (idempotent).

    Returns the number of complexes created.
    """
    sites = db.query(IndustrialSite).all()
    if not sites:
        print("[Clustering] No industrial sites found. Run OSM ingestion + seed layer first.")
        return 0

    print(f"[Clustering] Running DBSCAN on {len(sites)} industrial sites (eps={CLUSTER_RADIUS_KM}km)...")

    # Fetch centroids via PostGIS for precision
    rows = db.execute(text("""
        SELECT site_id, name, facility_type,
               ST_Y(centroid::geometry) AS lat,
               ST_X(centroid::geometry) AS lon
        FROM industrial_sites
        WHERE centroid IS NOT NULL
    """)).fetchall()

    if not rows:
        print("[Clustering] No centroid geometries found.")
        return 0

    site_ids   = [r[0] for r in rows]
    names      = [r[1] or "Unknown" for r in rows]
    ftypes     = [r[2] or "Industrial" for r in rows]
    lats       = np.array([r[3] for r in rows], dtype=float)
    lons       = np.array([r[4] for r in rows], dtype=float)

    coords_rad = _haversine_matrix_rad(lats, lons)
    eps_rad    = CLUSTER_RADIUS_KM / EARTH_RADIUS_KM

    db_model = DBSCAN(eps=eps_rad, min_samples=1, algorithm="ball_tree", metric="haversine")
    labels   = db_model.fit_predict(coords_rad)

    # Rebuild facility_complexes table
    db.query(FacilityComplex).delete()
    db.commit()

    n_clusters   = int(labels.max()) + 1
    complexes_added = 0

    for cluster_id in range(n_clusters):
        mask    = labels == cluster_id
        c_lats  = lats[mask]
        c_lons  = lons[mask]
        c_names = [names[i] for i, m in enumerate(mask) if m]
        c_ftypes = [ftypes[i] for i, m in enumerate(mask) if m]

        cen_lat = float(np.mean(c_lats))
        cen_lon = float(np.mean(c_lons))

        # Dominant name: longest (usually most descriptive)
        dom_name  = max(c_names, key=len)
        # Dominant type: most frequent
        from collections import Counter
        dom_type  = Counter(c_ftypes).most_common(1)[0][0]

        # Bounding radius: max great-circle distance from centroid to any member
        def _haversine_km(lat1, lon1, lat2, lon2):
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a    = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
            return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)) * 1000  # metres

        radii = [_haversine_km(cen_lat, cen_lon, la, lo) for la, lo in zip(c_lats, c_lons)]
        bounding_radius_m = float(max(radii)) if radii else 0.0

        fc = FacilityComplex(
            name=dom_name,
            facility_type=dom_type,
            member_count=int(mask.sum()),
            centroid_lat=cen_lat,
            centroid_lon=cen_lon,
            centroid_geom=f"SRID=4326;POINT({cen_lon} {cen_lat})",
            radius_m=bounding_radius_m,
            source="DBSCAN",
        )
        db.add(fc)
        complexes_added += 1

    db.commit()
    print(f"[Clustering] Created {complexes_added} facility complexes from {len(rows)} sites.")
    return complexes_added
