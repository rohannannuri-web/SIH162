from app.models.database import engine
from sqlalchemy import text
from init_db import init_db

with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS fused_event_scores CASCADE;'))
    conn.commit()

init_db()
