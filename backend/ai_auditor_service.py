from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


def _read_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        env_key, env_value = line.split("=", 1)
        if env_key.strip() != key:
            continue
        return env_value.strip().strip('"').strip("'")
    return None


def _generate_audit_prompt(
    subject_name: str,
    course_text: str,
    bibliography_text: str,
    current_year: int,
) -> str:
    lower_year = current_year - 5
    return (
        "Esti un Auditor Academic AI. Rolul tau este sa evaluezi calitatea unei Fise de Disciplina.\n\n"
        f'Materia evaluata: "{subject_name}"\n\n'
        "--- TEMATICA CURS ---\n"
        f"{course_text}\n\n"
        "--- BIBLIOGRAFIE ---\n"
        f"{bibliography_text}\n\n"
        "Sarcini:\n"
        '1. CONTINUT VAG: Analizeaza tematica. Este prea generica? Contine doar termeni precum "Introducere", "Partea 1"? '
        'Daca da, marcheaz-o ca "VAG" si ofera 2 propuneri specifice de imbunatatire. '
        'Daca e okay, marcheaz-o "DETALIAT".\n'
        f"2. BIBLIOGRAFIE: Extrage anii din bibliografie. Consideram anul curent {current_year}. "
        f"Daca nu exista NICIUN titlu publicat in ultimii 5 ani ({lower_year}-{current_year}), "
        'marcheaz-o ca "INVECHITA". Altfel, "ACTUALIZATA".\n\n'
        "Trebuie sa raspunzi STRICT in acest format JSON:\n"
        "{\n"
        '  "audit_tematica": {\n'
        '    "status": "VAG" | "DETALIAT",\n'
        '    "explicatie": "de ce este vag sau detaliat",\n'
        '    "sugestii_imbunatatire": ["Sugestia 1", "Sugestia 2"]\n'
        "  },\n"
        '  "audit_bibliografie": {\n'
        '    "status": "INVECHITA" | "ACTUALIZATA",\n'
        '    "cel_mai_nou_an_gasit": 2018,\n'
        '    "explicatie": "motivul deciziei"\n'
        "  }\n"
        "}\n"
    )


def _safe_text(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    value_clean = value.strip()
    return value_clean if value_clean else fallback


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    text_clean = (text or "").strip()
    if not text_clean:
        return None

    try:
        payload = json.loads(text_clean)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text_clean)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _run_gemini_audit(prompt: str, api_key: str) -> dict[str, Any] | None:
    try:
        import google.generativeai as genai  # type: ignore
    except ModuleNotFoundError:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-flash-latest")
        response = model.generate_content(prompt)
        response_text = _safe_text(getattr(response, "text", ""), "")
        return _extract_json_from_text(response_text)
    except Exception:
        return None


def _build_rule_based_topic_audit(course_text: str, subject_name: str) -> dict[str, Any]:
    text = _safe_text(course_text, "")
    text_lower = text.lower()
    tokens = re.findall(r"[a-zA-Z0-9]+", text_lower)
    token_count = len(tokens)
    generic_markers = [
        "introducere",
        "partea",
        "generalitati",
        "tematica",
        "diverse",
        "capitol",
        "notiuni",
        "sintetica",
    ]
    marker_hits = sum(1 for marker in generic_markers if marker in text_lower)
    has_enumeration = bool(re.search(r"(\n|^)\s*(\d+[\.\)]|[-*])\s+", text))

    is_vague = token_count < 60 or (marker_hits >= 2 and not has_enumeration)
    if is_vague:
        return {
            "status": "VAG",
            "explicatie": (
                "Tematica include formulare prea generale si nu detaliaza suficient obiectivele, "
                "subiectele sau rezultatele de invatare."
            ),
            "sugestii_imbunatatire": [
                f"Defineste 8-12 teme concrete pentru {subject_name}, fiecare cu obiective clare.",
                "Adauga pentru fiecare tema minim 2 concepte-cheie si un exemplu de aplicatie practica.",
            ],
        }

    return {
        "status": "DETALIAT",
        "explicatie": "Tematica este suficient de specifica si acopera explicit subiectele principale.",
        "sugestii_imbunatatire": [
            "Pastreaza structura actuala si actualizeaza anual exemplele aplicative.",
            "Leaga fiecare tema de metode de evaluare si de competentele vizate.",
        ],
    }


def _build_rule_based_bibliography_audit(bibliography_text: str, current_year: int) -> dict[str, Any]:
    text = _safe_text(bibliography_text, "")
    years = [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    newest_year = max(years) if years else None
    recent_year_limit = current_year - 5

    if newest_year is None:
        return {
            "status": "INVECHITA",
            "cel_mai_nou_an_gasit": None,
            "explicatie": "Nu au fost identificati ani de publicare in bibliografie.",
        }

    if newest_year < recent_year_limit:
        return {
            "status": "INVECHITA",
            "cel_mai_nou_an_gasit": newest_year,
            "explicatie": (
                f"Cea mai recenta sursa identificata este din {newest_year}, sub pragul {recent_year_limit}-{current_year}."
            ),
        }

    return {
        "status": "ACTUALIZATA",
        "cel_mai_nou_an_gasit": newest_year,
        "explicatie": f"Exista cel putin o sursa recenta (an {newest_year}).",
    }


def _normalize_ai_payload(
    ai_payload: dict[str, Any] | None,
    fallback_topic: dict[str, Any],
    fallback_bibliography: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if not isinstance(ai_payload, dict):
        return fallback_topic, fallback_bibliography, "rule_based"

    topic = ai_payload.get("audit_tematica")
    bibliography = ai_payload.get("audit_bibliografie")
    if not isinstance(topic, dict) or not isinstance(bibliography, dict):
        return fallback_topic, fallback_bibliography, "rule_based"

    topic_status = str(topic.get("status", "")).strip().upper()
    bibliography_status = str(bibliography.get("status", "")).strip().upper()

    if topic_status not in {"VAG", "DETALIAT"}:
        topic_status = str(fallback_topic.get("status", "VAG"))
    if bibliography_status not in {"INVECHITA", "ACTUALIZATA"}:
        bibliography_status = str(fallback_bibliography.get("status", "INVECHITA"))

    topic_explanation = _safe_text(topic.get("explicatie"), str(fallback_topic.get("explicatie", "")))
    bibliography_explanation = _safe_text(
        bibliography.get("explicatie"),
        str(fallback_bibliography.get("explicatie", "")),
    )

    suggestions = topic.get("sugestii_imbunatatire")
    if not isinstance(suggestions, list):
        suggestions = fallback_topic.get("sugestii_imbunatatire", [])
    normalized_suggestions = [str(item).strip() for item in suggestions if str(item).strip()]
    if not normalized_suggestions:
        normalized_suggestions = list(fallback_topic.get("sugestii_imbunatatire", []))

    newest_year = bibliography.get("cel_mai_nou_an_gasit")
    if newest_year is None:
        normalized_year = fallback_bibliography.get("cel_mai_nou_an_gasit")
    else:
        try:
            normalized_year = int(newest_year)
        except (TypeError, ValueError):
            normalized_year = fallback_bibliography.get("cel_mai_nou_an_gasit")

    normalized_topic = {
        "status": topic_status,
        "explicatie": topic_explanation,
        "sugestii_imbunatatire": normalized_suggestions[:4],
    }
    normalized_bibliography = {
        "status": bibliography_status,
        "cel_mai_nou_an_gasit": normalized_year,
        "explicatie": bibliography_explanation,
    }
    return normalized_topic, normalized_bibliography, "gemini"


def list_ai_auditor_subjects(db_path: Path) -> list[dict[str, Any]]:
    resolved_db_path = db_path.expanduser().resolve()
    if not resolved_db_path.exists():
        raise FileNotFoundError(f"Database file not found: {resolved_db_path}")

    conn = sqlite3.connect(resolved_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, nume
            FROM fisa_discipline
            ORDER BY LOWER(nume), id
            """
        ).fetchall()
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        subject_id = int(row["id"])
        subject_name = _safe_text(row["nume"], f"Disciplina #{subject_id}")
        results.append({"id": subject_id, "name": subject_name})
    return results


def run_ai_auditor_for_subject(
    *,
    fisa_id: int,
    db_path: Path,
    project_root: Path,
    current_year: int,
    allow_ai: bool = True,
) -> dict[str, Any]:
    resolved_db_path = db_path.expanduser().resolve()
    if not resolved_db_path.exists():
        raise FileNotFoundError(f"Database file not found: {resolved_db_path}")

    conn = sqlite3.connect(resolved_db_path)
    conn.row_factory = sqlite3.Row
    try:
        subject_row = conn.execute(
            "SELECT id, nume FROM fisa_discipline WHERE id = ?",
            (int(fisa_id),),
        ).fetchone()
        if not subject_row:
            raise ValueError(f"Subject not found for id={fisa_id}")

        course_row = conn.execute(
            """
            SELECT continut
            FROM fisa_sectiuni
            WHERE fisa_id = ? AND tip_sectiune IN ('curs', 'continut', 'descriere')
            ORDER BY CASE tip_sectiune
                WHEN 'curs' THEN 1
                WHEN 'continut' THEN 2
                WHEN 'descriere' THEN 3
                ELSE 99
            END
            LIMIT 1
            """,
            (int(fisa_id),),
        ).fetchone()
        bibliography_row = conn.execute(
            """
            SELECT continut
            FROM fisa_sectiuni
            WHERE fisa_id = ? AND tip_sectiune = 'bibliografie'
            LIMIT 1
            """,
            (int(fisa_id),),
        ).fetchone()
    finally:
        conn.close()

    subject_name = _safe_text(subject_row["nume"], f"Disciplina #{fisa_id}")
    course_text = _safe_text(course_row["continut"] if course_row else None, "Nu exista tematica.")
    bibliography_text = _safe_text(
        bibliography_row["continut"] if bibliography_row else None,
        "Nu exista bibliografie.",
    )

    rule_topic = _build_rule_based_topic_audit(course_text, subject_name)
    rule_bibliography = _build_rule_based_bibliography_audit(bibliography_text, current_year=current_year)

    prompt = _generate_audit_prompt(
        subject_name=subject_name,
        course_text=course_text,
        bibliography_text=bibliography_text,
        current_year=current_year,
    )

    api_key = os.getenv("GEMINI_API_KEY") or _read_env_value(project_root / ".env", "GEMINI_API_KEY")
    ai_payload = _run_gemini_audit(prompt, api_key) if allow_ai and api_key else None

    audit_topic, audit_bibliography, source = _normalize_ai_payload(
        ai_payload,
        fallback_topic=rule_topic,
        fallback_bibliography=rule_bibliography,
    )

    return {
        "fisa_id": int(fisa_id),
        "nume_materie": subject_name,
        "audit_tematica": audit_topic,
        "audit_bibliografie": audit_bibliography,
        "source": source,
    }


def run_ai_auditor_for_all_subjects(
    *,
    db_path: Path,
    project_root: Path,
    current_year: int,
    allow_ai: bool = False,
) -> dict[str, Any]:
    subjects = list_ai_auditor_subjects(db_path)
    rows: list[dict[str, Any]] = []

    problem_count = 0
    ok_count = 0
    for subject in subjects:
        result = run_ai_auditor_for_subject(
            fisa_id=int(subject["id"]),
            db_path=db_path,
            project_root=project_root,
            current_year=current_year,
            allow_ai=allow_ai,
        )
        topic_status = str(result.get("audit_tematica", {}).get("status", "")).upper()
        bibliography_status = str(result.get("audit_bibliografie", {}).get("status", "")).upper()
        is_problem = topic_status == "VAG" or bibliography_status == "INVECHITA"
        result["is_problem"] = is_problem
        rows.append(result)
        if is_problem:
            problem_count += 1
        else:
            ok_count += 1

    return {
        "summary": {
            "total": len(rows),
            "problem": problem_count,
            "ok": ok_count,
        },
        "rows": rows,
    }
