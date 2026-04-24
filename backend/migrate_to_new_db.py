#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


SRC = Path("backend/data/discipline.db")
DST = Path("backend/data/discipline_new.db")


def normalize_key(cod, nume, semestru, credite):
    return (cod or "", (nume or "").strip().lower(), int(semestru) if semestru is not None else None, int(credite) if credite is not None else None)


def migrate_only_missing(src: Path, dst: Path) -> dict:
    if not src.exists():
        raise FileNotFoundError(f"Source DB not found: {src}")
    if not dst.exists():
        raise FileNotFoundError(f"Destination DB not found: {dst}")

    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)
    try:
        src_cur = src_conn.cursor()
        dst_cur = dst_conn.cursor()

        # load existing plan keys
        dst_cur.execute("SELECT cod, nume, semestru, credite FROM plan_discipline")
        existing_plans = {tuple(r) for r in dst_cur.fetchall()}

        # migrate plan_discipline rows that are missing
        src_cur.execute("SELECT cod, nume, semestru, credite FROM plan_discipline")
        plans = src_cur.fetchall()
        inserted_plans = 0
        for row in plans:
            if tuple(row) not in existing_plans:
                dst_cur.execute("INSERT INTO plan_discipline (cod, nume, semestru, credite) VALUES (?, ?, ?, ?)", row)
                inserted_plans += 1

        # prepare fisa_discipline existing data
        dst_cur.execute("SELECT id, cod, nume, semestru, credite FROM fisa_discipline")
        dst_rows = dst_cur.fetchall()
        dst_ids = {r[0] for r in dst_rows}
        dst_keys = {normalize_key(r[1], r[2], r[3], r[4]): r[0] for r in dst_rows}

        # migrate fisa_discipline: preserve ids when possible, otherwise map to new ids
        src_cols = [r[1] for r in src_cur.execute("PRAGMA table_info('fisa_discipline')").fetchall()]
        has_eval = "evaluare_format" in src_cols
        has_ore_s = "ore_saptamana" in src_cols
        has_total = "total_ore_plan" in src_cols

        select_parts = ["id", "cod", "nume", "semestru", "credite"]
        select_parts.append("evaluare_format" if has_eval else "NULL")
        select_parts.append("ore_saptamana" if has_ore_s else "NULL")
        select_parts.append("total_ore_plan" if has_total else "NULL")
        select_stmt = "SELECT " + ", ".join(select_parts) + " FROM fisa_discipline"
        src_cur.execute(select_stmt)
        src_fise = src_cur.fetchall()
        id_map: dict[int, int] = {}
        inserted_fise = 0
        for row in src_fise:
            src_id, cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan = row
            key = normalize_key(cod, nume, semestru, credite)
            if src_id in dst_ids:
                id_map[src_id] = src_id
                continue
            if key in dst_keys:
                # map to existing dst id with same content
                id_map[src_id] = dst_keys[key]
                continue

            # try to insert preserving id
            try:
                dst_cur.execute(
                    "INSERT INTO fisa_discipline (id, cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (src_id, cod, nume, semestru, credite, evaluare_format or None, ore_saptamana, total_ore_plan),
                )
                id_map[src_id] = src_id
                dst_ids.add(src_id)
                inserted_fise += 1
            except sqlite3.IntegrityError:
                # id conflict: insert without id and map to new id
                dst_cur.execute(
                    "INSERT INTO fisa_discipline (cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cod, nume, semestru, credite, evaluare_format or None, ore_saptamana, total_ore_plan),
                )
                new_id = dst_cur.lastrowid
                id_map[src_id] = new_id
                inserted_fise += 1

        # update sqlite_sequence for fisa_discipline to max id
        try:
            dst_cur.execute("SELECT MAX(id) FROM fisa_discipline")
            max_id = dst_cur.fetchone()[0] or 0
            dst_cur.execute("DELETE FROM sqlite_sequence WHERE name = 'fisa_discipline'")
            if max_id:
                dst_cur.execute("INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES (?, ?)", ("fisa_discipline", max_id))
        except Exception:
            pass

        # migrate fisa_sectiuni using id_map
        src_cur.execute("SELECT fisa_id, tip_sectiune, continut FROM fisa_sectiuni")
        src_sects = src_cur.fetchall()
        inserted_sects = 0
        for fisa_id, tip, continut in src_sects:
            if fisa_id not in id_map:
                # source fisa was not migrated and no mapping; skip
                continue
            dst_fid = id_map[fisa_id]
            # check if already exists
            dst_cur.execute("SELECT 1 FROM fisa_sectiuni WHERE fisa_id=? AND tip_sectiune=? AND continut=? LIMIT 1", (dst_fid, tip, continut))
            if dst_cur.fetchone():
                continue
            dst_cur.execute("INSERT INTO fisa_sectiuni (fisa_id, tip_sectiune, continut) VALUES (?, ?, ?)", (dst_fid, tip, continut))
            inserted_sects += 1

        dst_conn.commit()

        return {
            "inserted_plans": inserted_plans,
            "inserted_fise": inserted_fise,
            "inserted_sectiuni": inserted_sects,
        }
    finally:
        src_conn.close()
        dst_conn.close()


if __name__ == "__main__":
    try:
        res = migrate_only_missing(SRC, DST)
        print(json.dumps({"status": "ok", "result": res}, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
