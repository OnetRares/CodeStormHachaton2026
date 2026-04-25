#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


DB = Path("backend/data/discipline_new.db")
WEEKS = 14
PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*%")


def _table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _table_columns(cur: sqlite3.Cursor, table_name: str) -> set[str]:
    if not _table_exists(cur, table_name):
        return set()
    rows = cur.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {str(col[1]) for col in rows}


def _extract_weight_values(text: str) -> list[int]:
    if not isinstance(text, str):
        return []
    out: list[int] = []
    for match in PERCENT_RE.finditer(text):
        try:
            value = int(match.group(1))
        except Exception:
            continue
        if 0 <= value <= 100:
            out.append(value)
    return out


def find_evaluation_sections(cur: sqlite3.Cursor, fisa_id: int) -> list[dict]:
    if not _table_exists(cur, "fisa_sectiuni"):
        return []

    rows = cur.execute(
        "SELECT tip_sectiune, continut FROM fisa_sectiuni WHERE fisa_id = ?",
        (fisa_id,),
    ).fetchall()
    matches: list[dict] = []
    for tip, continut in rows:
        tip_text = str(tip or "")
        lower = (continut or "").lower()
        if (
            "evaluare" in tip_text.lower()
            or "evaluare" in lower
            or "ponder" in lower
            or "ponderi" in lower
            or re.search(r"\d+%", lower)
        ):
            matches.append({"tip": tip_text, "continut": continut or ""})
    return matches


def check_db(db_path: Path) -> dict:
    if not db_path.exists():
        return {"status": "error", "error": f"DB not found: {db_path}"}

    out_rows: list[dict] = []
    legacy_mismatched_hours: list[dict] = []
    legacy_missing_hours: list[dict] = []
    legacy_evaluation_texts: list[dict] = []
    legacy_no_evaluation_section: list[dict] = []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    fisa_cols = _table_columns(cur, "fisa_discipline")
    if not fisa_cols:
        conn.close()
        return {"status": "error", "error": "Table fisa_discipline not found in database"}

    select_parts = [
        "id",
        "cod",
        "nume",
        "semestru",
        "credite",
        "evaluare_format" if "evaluare_format" in fisa_cols else "NULL AS evaluare_format",
        "ponderi_json" if "ponderi_json" in fisa_cols else "NULL AS ponderi_json",
        "ore_saptamana" if "ore_saptamana" in fisa_cols else "NULL AS ore_saptamana",
        "total_ore_plan" if "total_ore_plan" in fisa_cols else "NULL AS total_ore_plan",
    ]
    rows = cur.execute(
        f"SELECT {', '.join(select_parts)} FROM fisa_discipline ORDER BY id"
    ).fetchall()

    for row in rows:
        (
            fid,
            cod,
            nume,
            semestru,
            credite,
            evaluare_format,
            ponderi_json,
            ore_saptamana,
            total_ore_plan,
        ) = row

        base_rec = {
            "id": fid,
            "cod": cod,
            "nume": nume,
            "semestru": semestru,
            "credite": credite,
            "evaluare_format": evaluare_format,
            "ponderi_json": ponderi_json,
            "ore_saptamana": ore_saptamana,
            "total_ore_plan": total_ore_plan,
        }

        # Hours check: ore_saptamana * WEEKS == total_ore_plan
        hours_status = "ok"
        hours_message = "Formula este corecta."
        expected_total = None
        if ore_saptamana is None or total_ore_plan is None:
            hours_status = "missing"
            hours_message = "Campurile de ore lipsesc."
            legacy_missing_hours.append(base_rec)
        else:
            expected = ore_saptamana * WEEKS
            expected_total = expected
            if expected != total_ore_plan:
                hours_status = "not_ok"
                hours_message = (
                    f"ore_saptamana * {WEEKS} = {expected}, dar total_ore_plan este {total_ore_plan}."
                )
                mismatch = dict(base_rec)
                mismatch["expected_total"] = expected
                legacy_mismatched_hours.append(mismatch)

        # Weights check: sum(XX%) == 100 in evaluation-related sections
        eval_secs = find_evaluation_sections(cur, fid)
        if eval_secs:
            legacy_evaluation_texts.append({"fisa": base_rec, "sections": eval_secs})
        else:
            legacy_no_evaluation_section.append(base_rec)

        weight_values: list[int] = []
        weight_source = "none"
        if isinstance(ponderi_json, str) and ponderi_json.strip():
            try:
                parsed = json.loads(ponderi_json)
                if isinstance(parsed, list):
                    weight_values = [int(x) for x in parsed if str(x).strip() != ""]
                    weight_source = "ingestion.ponderi_json"
            except Exception:
                # Keep fallback strategy below.
                weight_values = []

        if not weight_values:
            for section in eval_secs:
                weight_values.extend(_extract_weight_values(section.get("continut", "")))
            if weight_values:
                weight_source = "fisa_sectiuni.regex"

        weights_status = "ok"
        weights_sum = sum(weight_values) if weight_values else None
        if not weight_values:
            weights_status = "missing"
            weights_message = "Nu s-au identificat ponderi procentuale in sectiunile de evaluare."
        elif weights_sum != 100:
            weights_status = "not_ok"
            weights_message = f"Suma ponderilor este {weights_sum}, dar trebuie sa fie 100."
        else:
            weights_message = "Suma ponderilor este 100."

        overall_status = "ok" if hours_status == "ok" and weights_status == "ok" else "not_ok"
        out_rows.append(
            {
                "id": fid,
                "cod": cod,
                "nume": nume,
                "semestru": semestru,
                "credite": credite,
                "overall_status": overall_status,
                "hours": {
                    "status": hours_status,
                    "ore_saptamana": ore_saptamana,
                    "total_ore_plan": total_ore_plan,
                    "expected_total": expected_total,
                    "message": hours_message,
                },
                "weights": {
                    "status": weights_status,
                    "values": weight_values,
                    "sum": weights_sum,
                    "sections_found": len(eval_secs),
                    "source": weight_source,
                    "message": weights_message,
                },
            }
        )

    conn.close()

    total = len(out_rows)
    ok_count = sum(1 for row in out_rows if row["overall_status"] == "ok")
    hours_ok = sum(1 for row in out_rows if row["hours"]["status"] == "ok")
    hours_not_ok = sum(1 for row in out_rows if row["hours"]["status"] == "not_ok")
    hours_missing = sum(1 for row in out_rows if row["hours"]["status"] == "missing")
    weights_ok = sum(1 for row in out_rows if row["weights"]["status"] == "ok")
    weights_not_ok = sum(1 for row in out_rows if row["weights"]["status"] == "not_ok")
    weights_missing = sum(1 for row in out_rows if row["weights"]["status"] == "missing")

    return {
        "status": "success",
        "db_path": str(db_path),
        "weeks": WEEKS,
        "summary": {
            "total": total,
            "ok": ok_count,
            "not_ok": total - ok_count,
            "hours_ok": hours_ok,
            "hours_not_ok": hours_not_ok,
            "hours_missing": hours_missing,
            "weights_ok": weights_ok,
            "weights_not_ok": weights_not_ok,
            "weights_missing": weights_missing,
        },
        "rows": out_rows,
        # Legacy fields kept for compatibility with previous script output.
        "checked": total,
        "mismatched_hours": legacy_mismatched_hours,
        "missing_hours": legacy_missing_hours,
        "evaluation_texts": legacy_evaluation_texts,
        "no_evaluation_section": legacy_no_evaluation_section,
    }


def main() -> int:
    res = check_db(DB)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
