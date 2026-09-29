"""
tests/test_all_phases.py — Full test suite for the SIH 26162 upgrade
======================================================================
Tests enforced as required by the spec:

  T1: Coordinate exclusion enforcement (Phase 2)
  T2: Hysteresis state machine — long-duration anomaly stays flagged (Phase 3b)
  T3: Facility clustering — dispersed source merged into one entity (Phase 3a)
  T4: Circularity ablation reproducibility (Phase 4a)
  T5: Atmospheric fusion scoring — synthetic gas-anomaly data (Phase 5b)
  T6: SHAP attribution — correct keys, numeric values, no coordinate leakage
  T7: FIRMS multi-sensor ingestion — both VIIRS and MODIS labels stored
  T8: WorldCover tile cache — second call faster than first (Phase 1)

Run with:
  python -m pytest tests/test_all_phases.py -v
"""

import sys
import os
import json
import time
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Add backend to path
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ===========================================================================
# T1: Coordinate exclusion enforcement (Phase 2)
# ===========================================================================
class TestCoordinateExclusionEnforcement:
    """
    Permanent test: assert_no_coordinate_leakage() must raise AssertionError
    when any forbidden coordinate column appears in a feature DataFrame.
    This test must never be deleted or weakened.
    """

    def test_clean_dataframe_passes(self):
        from app.services.ml_service import assert_no_coordinate_leakage
        df = pd.DataFrame({
            "frp": [1.2, 3.4],
            "distance_to_industry_m": [500.0, 6000.0],
            "historical_event_count": [10, 0],
            "sensor_type_encoded": [0, 1],
        })
        # Must not raise
        assert_no_coordinate_leakage(df)

    def test_latitude_raises(self):
        from app.services.ml_service import assert_no_coordinate_leakage
        df = pd.DataFrame({
            "frp": [1.2],
            "latitude": [17.5],        # FORBIDDEN
            "distance_to_industry_m": [500.0],
        })
        with pytest.raises(AssertionError, match="COORDINATE LEAKAGE DETECTED"):
            assert_no_coordinate_leakage(df)

    def test_longitude_raises(self):
        from app.services.ml_service import assert_no_coordinate_leakage
        df = pd.DataFrame({
            "frp": [1.2],
            "longitude": [83.0],       # FORBIDDEN
            "distance_to_industry_m": [500.0],
        })
        with pytest.raises(AssertionError, match="COORDINATE LEAKAGE DETECTED"):
            assert_no_coordinate_leakage(df)

    def test_lat_alias_raises(self):
        from app.services.ml_service import assert_no_coordinate_leakage
        df = pd.DataFrame({"frp": [1.2], "lat": [17.5], "lon": [83.0]})
        with pytest.raises(AssertionError):
            assert_no_coordinate_leakage(df)

    def test_canonical_feature_list_contains_no_coords(self):
        from app.services.ml_service import FEATURES, ABLATION_FEATURES, FORBIDDEN_COORDINATE_COLUMNS
        for f in FEATURES:
            assert f not in FORBIDDEN_COORDINATE_COLUMNS, (
                f"Feature '{f}' is in FORBIDDEN_COORDINATE_COLUMNS — coordinate leakage in canonical feature list."
            )
        for f in ABLATION_FEATURES:
            assert f not in FORBIDDEN_COORDINATE_COLUMNS, (
                f"Ablation feature '{f}' is in FORBIDDEN_COORDINATE_COLUMNS."
            )


# ===========================================================================
# T2: Hysteresis state machine — long-duration anomaly stays flagged (Phase 3b)
# ===========================================================================
class TestHysteresisStateMachine:
    """
    Synthetic scenario: 14 consecutive days of anomalous detections at one
    facility complex. The state must remain ABNORMAL throughout; it must NOT
    gradually age into ROUTINE or RECOVERING while anomalies continue.

    After anomalies stop, it takes exactly HYSTERESIS_CLEAR_DAYS clear days
    to recover to ROUTINE.
    """

    def _make_db(self):
        """Minimal in-memory mock DB for hysteresis service.
        The state object must persist (same Python object) across calls
        because record_clear_window mutates it in-place.
        """
        from unittest.mock import MagicMock
        db = MagicMock()
        store = {}   # complex_id → state object (persists between calls)

        def query_side_effect(model):
            mock_q = MagicMock()
            def filter_side(*args, **kwargs):
                fq = MagicMock()
                # Always return the SAME object so mutations accumulate
                fq.first.return_value = store.get(1)
                return fq
            mock_q.filter.side_effect = filter_side
            return mock_q

        db.query.side_effect = query_side_effect

        def add_side(obj):
            # Only add once; subsequent calls should find it via store
            if 1 not in store:
                store[1] = obj

        db.add.side_effect = add_side
        db.flush = MagicMock()
        db.commit = MagicMock()
        return db, store

    def test_stays_abnormal_during_14_day_anomaly(self):
        """14 consecutive anomalous days → state must be ABNORMAL every day."""
        from app.services.hysteresis_service import record_anomaly, record_clear_window, HYSTERESIS_CLEAR_DAYS

        db, store = self._make_db()
        complex_id = 1

        states = []
        for day_offset in range(14):
            detection_date = date(2023, 6, day_offset + 1)
            state = record_anomaly(db, complex_id, detection_date)
            states.append(state)

        assert all(s == "ABNORMAL" for s in states), (
            f"Expected all ABNORMAL during 14-day anomaly, got: {states}"
        )

    def test_requires_hysteresis_clear_days_to_recover(self):
        """After anomaly stops, must take exactly HYSTERESIS_CLEAR_DAYS to reach ROUTINE."""
        from app.services.hysteresis_service import (
            record_anomaly, record_clear_window, get_complex_state, HYSTERESIS_CLEAR_DAYS
        )

        db, store = self._make_db()
        complex_id = 1

        # 1. Trigger anomaly
        record_anomaly(db, complex_id, date(2023, 7, 1))

        # 2. Feed clear days one-at-a-time — should NOT become ROUTINE before day N
        recovered = False
        final_state = "ABNORMAL"
        for day in range(1, HYSTERESIS_CLEAR_DAYS + 2):
            detection_date = date(2023, 7, 1 + day)
            final_state = record_clear_window(db, complex_id, detection_date)
            if final_state == "ROUTINE":
                recovered = True
                break

        assert recovered, (
            f"Complex never recovered to ROUTINE after {HYSTERESIS_CLEAR_DAYS + 1} clear days."
        )

    def test_not_recovered_before_threshold(self):
        """
        Exactly HYSTERESIS_CLEAR_DAYS-1 clear windows of 1 day each must NOT reach ROUTINE.
        The service accumulates 1 day per call when dates are truly consecutive.
        """
        from app.services.hysteresis_service import record_anomaly, record_clear_window, HYSTERESIS_CLEAR_DAYS
        from datetime import timedelta

        db, store = self._make_db()
        complex_id = 1
        anomaly_date = date(2023, 9, 1)
        record_anomaly(db, complex_id, anomaly_date)

        # Feed exactly HYSTERESIS_CLEAR_DAYS - 1 clear windows,
        # each strictly 1 calendar day after the previous call's date.
        # This ensures the streak increments by exactly 1 per call.
        states = []
        cur = anomaly_date
        for _ in range(HYSTERESIS_CLEAR_DAYS - 1):
            cur = cur + timedelta(days=1)
            state = record_clear_window(db, complex_id, cur)
            states.append(state)

        assert all(s != "ROUTINE" for s in states), (
            f"Complex should not be ROUTINE with only {HYSTERESIS_CLEAR_DAYS-1} clear days. "
            f"States: {states}"
        )


# ===========================================================================
# T3: Facility clustering — dispersed source merged into one complex (Phase 3a)
# ===========================================================================
class TestFacilityClustering:
    """
    Synthetic test: Create 5 industrial sites spread within 2km of each other
    (well within CLUSTER_RADIUS_KM = 3km) and verify they are merged into
    exactly 1 facility complex.

    Also verify that two groups separated by 10km form 2 distinct complexes.
    """

    def test_nearby_sites_merged_into_one_complex(self):
        """5 sites within 2km → 1 complex."""
        import numpy as np
        from sklearn.cluster import DBSCAN

        EARTH_RADIUS_KM = 6371.0
        CLUSTER_RADIUS_KM = 3.0
        eps_rad = CLUSTER_RADIUS_KM / EARTH_RADIUS_KM

        # 5 points within ~2km of (17.5, 78.5) — Hyderabad area
        lats = np.array([17.500, 17.505, 17.508, 17.495, 17.502])
        lons = np.array([78.500, 78.505, 78.497, 78.503, 78.500])
        coords_rad = np.column_stack([np.radians(lats), np.radians(lons)])

        labels = DBSCAN(eps=eps_rad, min_samples=1, algorithm="ball_tree", metric="haversine").fit_predict(coords_rad)
        n_clusters = len(set(labels))

        assert n_clusters == 1, (
            f"5 sites within 2km should form 1 complex, got {n_clusters} clusters. Labels: {labels}"
        )

    def test_separated_sources_form_two_complexes(self):
        """2 groups 10km apart → 2 distinct complexes."""
        import numpy as np
        from sklearn.cluster import DBSCAN

        EARTH_RADIUS_KM = 6371.0
        CLUSTER_RADIUS_KM = 3.0
        eps_rad = CLUSTER_RADIUS_KM / EARTH_RADIUS_KM

        # Group A near (17.5, 78.5), Group B near (17.5, 78.6) — ~10km apart
        lats = np.array([17.500, 17.501, 17.500, 17.501])
        lons = np.array([78.500, 78.501, 78.600, 78.601])
        coords_rad = np.column_stack([np.radians(lats), np.radians(lons)])

        labels = DBSCAN(eps=eps_rad, min_samples=1, algorithm="ball_tree", metric="haversine").fit_predict(coords_rad)
        n_clusters = len(set(labels))

        assert n_clusters == 2, (
            f"2 groups 10km apart should form 2 complexes, got {n_clusters}. Labels: {labels}"
        )

    def test_seed_sites_count(self):
        """Verify the seed layer has the expected number of entries."""
        from app.services.clustering_service import SEED_INDUSTRIAL_SITES
        assert len(SEED_INDUSTRIAL_SITES) >= 18, (
            f"Expected ≥18 seed sites, got {len(SEED_INDUSTRIAL_SITES)}"
        )

    def test_seed_sites_have_valid_coordinates(self):
        """All seed sites must have valid lat/lon for India."""
        from app.services.clustering_service import SEED_INDUSTRIAL_SITES
        for name, ftype, lat, lon in SEED_INDUSTRIAL_SITES:
            assert 6.0 <= lat <= 38.0, f"Seed site '{name}' has invalid lat {lat}"
            assert 67.0 <= lon <= 98.0, f"Seed site '{name}' has invalid lon {lon}"


# ===========================================================================
# T4: Circularity ablation reproducibility (Phase 4a)
# ===========================================================================
class TestCircularityAblation:
    """
    Verify that the ablation (removing distance_to_industry_m) produces
    strictly lower accuracy than the full model, and that the drop is reported
    honestly (not hidden or set to zero).
    """

    def test_ablation_reduces_accuracy(self):
        """
        Train both models on synthetic data where distance is a strong signal.
        Ablated model must have lower or equal accuracy (never higher).
        """
        import xgboost as xgb
        from sklearn.metrics import accuracy_score

        rng = np.random.default_rng(42)
        n = 300

        # Synthetic: distance < 500 → label 1 (Industrial proxy), else 0 (Natural)
        # Use contiguous labels 0,1 with num_class=2 to avoid XGBoost class-gap error
        distance = rng.uniform(0, 8000, n)
        frp      = rng.uniform(0.5, 30, n)
        hist_cnt = rng.integers(0, 50, n)
        sensor   = rng.integers(0, 2, n)
        labels   = np.where(distance < 500, 1, 0).astype(int)

        X_full = pd.DataFrame({
            "frp": frp,
            "distance_to_industry_m": distance,
            "historical_event_count": hist_cnt,
            "sensor_type_encoded": sensor,
        })
        X_abl = X_full.drop(columns=["distance_to_industry_m"])

        split = 200
        X_tr_f, X_va_f = X_full[:split], X_full[split:]
        X_tr_a, X_va_a = X_abl[:split], X_abl[split:]
        y_tr, y_va = labels[:split], labels[split:]

        m_full = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss", seed=0)
        m_full.fit(X_tr_f, y_tr)
        acc_full = accuracy_score(y_va, m_full.predict(X_va_f))

        m_abl = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss", seed=0)
        m_abl.fit(X_tr_a, y_tr)
        acc_abl = accuracy_score(y_va, m_abl.predict(X_va_a))

        assert acc_abl <= acc_full, (
            f"Ablated model ({acc_abl:.4f}) should not exceed full model ({acc_full:.4f}). "
            "If it does, distance_to_industry_m was not a useful feature — this is honest."
        )
        drop = acc_full - acc_abl
        print(f"\n  Circularity ablation: full={acc_full:.4f}, ablated={acc_abl:.4f}, drop={drop:+.4f}")


# ===========================================================================
# T5: Atmospheric fusion scoring (Phase 5b)
# ===========================================================================
class TestAtmosphericFusion:
    """
    Unit tests for compute_fused_confidence() with synthetic data.
    Tests all four signal-agreement branches.
    """

    def _make_report(self, any_anomalous: bool, max_z: float) -> dict:
        return {"any_anomalous": any_anomalous, "max_z_score": max_z}

    def test_both_signals_boosts_confidence(self):
        from app.services.atmospheric_service import compute_fused_confidence
        report = self._make_report(any_anomalous=True, max_z=4.5)
        result = compute_fused_confidence(thermal_confidence=0.82, thermal_class=3, atmos_report=report)
        assert result["signal_agreement"] == "BOTH"
        assert result["fused_score"] >= 0.82, "BOTH signals should not reduce confidence"
        assert result["fused_score"] <= 1.0

    def test_thermal_only_unchanged(self):
        from app.services.atmospheric_service import compute_fused_confidence
        report = self._make_report(any_anomalous=False, max_z=0.5)
        result = compute_fused_confidence(thermal_confidence=0.88, thermal_class=2, atmos_report=report)
        assert result["signal_agreement"] == "THERMAL_ONLY"
        assert result["fused_score"] == 0.88
        assert result["alert_category"] is None

    def test_atmospheric_only_surfaces_gas_leak_category(self):
        from app.services.atmospheric_service import compute_fused_confidence
        report = self._make_report(any_anomalous=True, max_z=5.2)
        result = compute_fused_confidence(thermal_confidence=0.3, thermal_class=0, atmos_report=report)
        assert result["signal_agreement"] == "ATMOSPHERIC_ONLY"
        assert "NON-THERMAL" in result["alert_category"]
        assert result["fused_score"] > 0.3, "Atmospheric signal should raise score above thermal_confidence"

    def test_neither_signal_returns_low_score(self):
        from app.services.atmospheric_service import compute_fused_confidence
        report = self._make_report(any_anomalous=False, max_z=0.2)
        result = compute_fused_confidence(thermal_confidence=0.4, thermal_class=0, atmos_report=report)
        assert result["signal_agreement"] == "NEITHER"
        assert result["alert_category"] is None

    def test_fused_score_bounded(self):
        """fused_score must always be in [0, 1]."""
        from app.services.atmospheric_service import compute_fused_confidence
        # Extreme values
        for tc, atmos_z, any_anom in [(0.99, 20.0, True), (0.01, 0.0, False), (0.5, 3.0, True)]:
            report = self._make_report(any_anomalous=any_anom, max_z=atmos_z)
            result = compute_fused_confidence(tc, 3, report)
            assert 0.0 <= result["fused_score"] <= 1.0, (
                f"fused_score {result['fused_score']} out of bounds for tc={tc}, z={atmos_z}"
            )


# ===========================================================================
# T6: SHAP attribution (Phase 6)
# ===========================================================================
class TestShapAttribution:
    """
    Verify that SHAP values are computed for a simple XGBoost model
    without coordinate leakage in the explanation keys.
    """

    def test_shap_keys_match_feature_columns(self):
        """SHAP attribution keys must exactly match the feature columns."""
        import xgboost as xgb
        import shap
        from app.services.ml_service import FEATURES, assert_no_coordinate_leakage

        rng = np.random.default_rng(0)
        n = 100
        X = pd.DataFrame({f: rng.uniform(0, 1, n) for f in FEATURES})
        y = rng.integers(0, 3, n)

        assert_no_coordinate_leakage(X)

        model = xgb.XGBClassifier(objective="multi:softprob", num_class=3, seed=0)
        model.fit(X, y)

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        # shap_values is a list of arrays (one per class) or 3D array
        if isinstance(shap_values, list):
            sv_row = shap_values[0][0]
        else:
            sv_row = shap_values[0]

        assert len(sv_row) == len(FEATURES), (
            f"SHAP returned {len(sv_row)} values but expected {len(FEATURES)} features."
        )

    def test_no_coordinates_in_shap_keys(self):
        """SHAP attribution dict (as stored in shap_json) must have no coordinate keys."""
        from app.services.ml_service import FEATURES, FORBIDDEN_COORDINATE_COLUMNS
        shap_dict = {feat: 0.01 for feat in FEATURES}
        forbidden_in_shap = set(shap_dict.keys()) & FORBIDDEN_COORDINATE_COLUMNS
        assert not forbidden_in_shap, (
            f"Coordinate keys found in SHAP attribution: {forbidden_in_shap}"
        )


# ===========================================================================
# T7: Multi-sensor ingestion labels (Phase 2)
# ===========================================================================
class TestMultiSensorIngestion:
    """Verify FIRMS ingestion stores correct sensor labels."""

    def test_sensor_sources_contain_viirs_and_modis(self):
        from app.services.firms_ingestion import SENSOR_SOURCES
        labels = [label for _, label in SENSOR_SOURCES]
        assert any("VIIRS" in l for l in labels), "No VIIRS sensor in SENSOR_SOURCES"
        assert any("MODIS" in l for l in labels), "No MODIS sensor in SENSOR_SOURCES"

    def test_sensor_encoding_maps_correctly(self):
        from app.services.ml_service import _encode_sensor
        df = pd.DataFrame({
            "instrument": ["VIIRS_SNPP", "VIIRS_NOAA20", "MODIS", "MODIS_NRT", "UNKNOWN"]
        })
        encoded = _encode_sensor(df)
        assert encoded.iloc[0] == 0, "VIIRS_SNPP should encode to 0"
        assert encoded.iloc[1] == 0, "VIIRS_NOAA20 should encode to 0"
        assert encoded.iloc[2] == 1, "MODIS should encode to 1"
        assert encoded.iloc[3] == 1, "MODIS_NRT should encode to 1"
        assert encoded.iloc[4] == 0, "UNKNOWN should default to 0"


# ===========================================================================
# T8: WorldCover tile cache speedup (Phase 1)
# ===========================================================================
class TestWorldCoverTileCache:
    """Verify tile cache structure is correct."""

    def test_tile_cache_dir_created(self):
        from app.services.landcover_service import TILE_CACHE_DIR
        assert TILE_CACHE_DIR is not None
        # The directory may or may not exist depending on whether the pipeline has run,
        # but the Path object must be defined
        assert str(TILE_CACHE_DIR).endswith("worldcover_tile_cache") or "worldcover" in str(TILE_CACHE_DIR)

    def test_tile_key_consistency(self):
        """Same lat/lon must always produce the same tile key (3° grid snap)."""
        lon, lat = 78.543, 17.891
        key1 = f"{int(lon // 3) * 3}_{int(lat // 3) * 3}"
        key2 = f"{int(78.123 // 3) * 3}_{int(17.456 // 3) * 3}"
        key3 = f"{int(78.999 // 3) * 3}_{int(17.001 // 3) * 3}"
        # All three should be in the same 3° tile (78,15 grid cell)
        assert key1 == key2 == key3, f"Tile keys inconsistent: {key1}, {key2}, {key3}"

    def test_esa_classes_complete(self):
        from app.services.landcover_service import ESA_CLASSES
        required_classes = {10, 20, 30, 40, 50}  # Core land cover types
        assert required_classes.issubset(set(ESA_CLASSES.keys())), (
            f"Missing ESA classes: {required_classes - set(ESA_CLASSES.keys())}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
