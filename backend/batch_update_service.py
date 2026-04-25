#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

def batch_update_text(db_path: Path, old_text: str, new_text: str) -> Dict[str, int]:
    """
    Performs a global find-and-replace in the database.
    Targets:
    - plan_discipline.nume
    - fisa_discipline.nume
    - fisa_sectiuni.continut
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    stats = {
        "plan_discipline": 0,
        "fisa_discipline": 0,
        "fisa_sectiuni": 0
    }

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Update plan_discipline
        cursor.execute(
            "UPDATE plan_discipline SET nume = REPLACE(nume, ?, ?) WHERE nume LIKE ?",
            (old_text, new_text, f"%{old_text}%")
        )
        stats["plan_discipline"] = cursor.rowcount

        # Update fisa_discipline
        cursor.execute(
            "UPDATE fisa_discipline SET nume = REPLACE(nume, ?, ?) WHERE nume LIKE ?",
            (old_text, new_text, f"%{old_text}%")
        )
        stats["fisa_discipline"] = cursor.rowcount

        # Update fisa_sectiuni
        cursor.execute(
            "UPDATE fisa_sectiuni SET continut = REPLACE(continut, ?, ?) WHERE continut LIKE ?",
            (old_text, new_text, f"%{old_text}%")
        )
        stats["fisa_sectiuni"] = cursor.rowcount

        conn.commit()

    return stats

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch update text in the database.")
    parser.add_argument("--db", default="backend/data/discipline.db", help="Path to the database file")
    parser.add_argument("--old", required=True, help="Text to search for")
    parser.add_argument("--new", required=True, help="Text to replace with")
    
    args = parser.parse_args()
    db_path = Path(args.db)
    
    try:
        results = batch_update_text(db_path, args.old, args.new)
        print(f"Update successful: {results}")
    except Exception as e:
        print(f"Error: {e}")
