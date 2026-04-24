#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


DB = Path("backend/data/discipline_new.db")
WEEKS = 14


def find_evaluation_sections(cur, fisa_id):
    rows = cur.execute(
        "SELECT tip_sectiune, continut FROM fisa_sectiuni WHERE fisa_id = ?",
        (fisa_id,),
    ).fetchall()
    matches = []
    for tip, continut in rows:
        lower = (continut or "").lower()
        if "evaluare" in lower or "ponder" in lower or "ponderi" in lower or re.search(r"\d+%", lower):
            matches.append({"tip": tip, "continut": continut})
    return matches


def check_db(db_path: Path) -> dict:
    if not db_path.exists():
        return {"error": f"DB not found: {db_path}"}
    out = {"checked": 0, "mismatched_hours": [], "missing_hours": [], "evaluation_texts": [], "no_evaluation_section": []}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan FROM fisa_discipline"
    ).fetchall()
    for row in rows:
        fid, cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan = row
        out["checked"] += 1
        rec = {"id": fid, "cod": cod, "nume": nume, "semestru": semestru, "credite": credite, "evaluare_format": evaluare_format, "ore_saptamana": ore_saptamana, "total_ore_plan": total_ore_plan}
        if ore_saptamana is None or total_ore_plan is None:
            out["missing_hours"].append(rec)
        else:
            expected = ore_saptamana * WEEKS
            if expected != total_ore_plan:
                rec["expected_total"] = expected
                out["mismatched_hours"].append(rec)

        eval_secs = find_evaluation_sections(cur, fid)
        if eval_secs:
            out["evaluation_texts"].append({"fisa": rec, "sections": eval_secs})
        else:
            out["no_evaluation_section"].append(rec)

    conn.close()
    return out


def main() -> int:
    res = check_db(DB)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
