"""
migrate_add_columns.py — Add columns introduced in the Phase 2/6 upgrade.
Run once. Idempotent (uses IF NOT EXISTS).
"""
from app.models.database import engine
from sqlalchemy import text

MIGRATIONS = [
    # Phase 2: sensor type feature column
    "ALTER TABLE event_features ADD COLUMN IF NOT EXISTS sensor_type VARCHAR(20)",
    # Phase 6: SHAP attribution JSON
    "ALTER TABLE event_features ADD COLUMN IF NOT EXISTS shap_json TEXT",
    # Phase 3b: last_clear_date for hysteresis streak tracking
    "ALTER TABLE facility_hysteresis ADD COLUMN IF NOT EXISTS last_clear_date VARCHAR(20)",
]

with engine.connect() as conn:
    for stmt in MIGRATIONS:
        conn.execute(text(stmt))
        print(f"  OK: {stmt[:60]}...")
    conn.commit()

print("Migration complete.")
