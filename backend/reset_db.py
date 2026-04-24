#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


TABLES_IN_DELETE_ORDER = [
    "fisa_sectiuni",
    "fisa_discipline",
    "plan_discipline",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset (truncate) discipline tables from SQLite database."
    )
    parser.add_argument(
        "--db-path",
        default="backend/data/discipline.db",
        help="Path to SQLite DB (default: backend/data/discipline.db)",
    )
    parser.add_argument(
        "--no-vacuum",
        action="store_true",
        help="Skip VACUUM after truncate.",
    )
    return parser.parse_args()


def reset_database(db_path: Path, vacuum: bool = True) -> dict:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    deleted_rows: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        for table in TABLES_IN_DELETE_ORDER:
            if table not in existing_tables:
                deleted_rows[table] = 0
                continue
            deleted_rows[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                0
            ]
            conn.execute(f"DELETE FROM {table}")

        if "sqlite_sequence" in existing_tables:
            for table in ("fisa_discipline",):
                conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

        conn.commit()
        if vacuum:
            conn.execute("VACUUM")

    return deleted_rows


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser().resolve()

    deleted_rows = reset_database(db_path, vacuum=not args.no_vacuum)
    print(f"Database reset complete: {db_path}")
    for table, count in deleted_rows.items():
        print(f"- {table}: deleted {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
