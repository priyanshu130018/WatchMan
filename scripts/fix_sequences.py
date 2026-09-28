"""Utility to synchronize all PostgreSQL sequences with their table max(id)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import text
from app.db.session import SessionLocal

def sync_sequences():
    db = SessionLocal()
    try:
        tables = ["contents", "genres", "content_genres", "content_languages", "watchman_decisions", "users", "reviews"]
        for tbl in tables:
            try:
                seq_name = db.execute(text("SELECT pg_get_serial_sequence(:tbl, 'id')"), {"tbl": tbl}).scalar()
                if seq_name:
                    max_id = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {tbl}")).scalar()
                    new_val = max(max_id, 1) + 1
                    db.execute(text("SELECT setval(:seq, :val, false)"), {"seq": seq_name, "val": new_val})
                    db.commit()
                    print(f"Synced {tbl}: sequence {seq_name} -> {new_val} (max_id was {max_id})")
            except Exception as e:
                db.rollback()
                print(f"Table {tbl} skipped or error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    sync_sequences()
