#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import fitz


@dataclass
class PlanRow:
    rowid: int
    cod: str | None
    nume: str
    semestru: int | None
    credite: int | None


@dataclass
class FdProbe:
    cod: str | None
    nume: str
    semestru: int | None
    credite: int | None


def remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_name(text: str) -> str:
    clean = remove_diacritics((text or "").lower())
    clean = re.sub(r"[^a-z0-9 ]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def canonicalize_course_name(text: str) -> str:
    base = normalize_spaces(remove_diacritics(text))
    squashed = re.sub(r"[^a-z0-9]+", "", base.lower())
    aliases = {
        "algoritmifundamentali": "algoritmi fundamentali",
        "notiunifundamentaledeinformatica": "notiuni fundamentale de informatica",
        "notiunifundamentaledematematica": "notiuni fundamentale de matematica",
        "eticasiintegritateacademicai": "etica si integritate academica",
    }
    return aliases.get(squashed, base)


def normalize_code(value: str | None) -> str:
    return re.sub(r"[^a-z0-9._/-]+", "", (value or "").lower())


def is_auto_code(value: str | None) -> bool:
    code = normalize_code(value)
    return not code or code.startswith("auto_") or code.startswith("fisa_")


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    return int(match.group(0))


def parse_semestru_token(raw: str | None) -> int | None:
    value = normalize_name(raw or "")
    if not value:
        return None
    first = value.split(" ", 1)[0]
    first = re.sub(r"[^0-9iv/-]", "", first)
    if first.startswith("1") or first == "i":
        return 1
    if first.startswith("2") or first == "ii":
        return 2
    if first in {"i-ii", "i/ii"}:
        return 1
    return None


def extract_text_native(pdf_path: Path) -> str:
    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def extract_field(text: str, patterns: list[str], keywords: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group("value").strip(" :-\t")
            if value:
                return value

    lines = text.splitlines()
    lowered = [normalize_name(line) for line in lines]
    normalized_keywords = [normalize_name(keyword) for keyword in keywords]
    for idx, line in enumerate(lowered):
        for keyword in normalized_keywords:
            if keyword not in line:
                continue
            tail = line.split(keyword, 1)[1].strip(" :-\t")
            if tail:
                return tail
            for look_ahead in range(idx + 1, min(idx + 5, len(lines))):
                candidate = normalize_spaces(lines[look_ahead])
                if candidate:
                    return candidate
    return ""


def parse_fd_probe(text: str) -> FdProbe:
    normalized_multiline = "\n".join(normalize_spaces(line) for line in text.splitlines())
    probe_text = remove_diacritics(normalized_multiline)
    norm = normalize_name(probe_text)

    nume_raw = extract_field(
        probe_text,
        patterns=[
            r"2\.1\s+denumirea disciplinei\s+(?P<value>[^\n]+)",
            r"(?:denumirea disciplinei|numele disciplinei|nume disciplina)\s*[:\-]\s*(?P<value>[^\n]+)",
        ],
        keywords=["2.1 denumirea disciplinei", "denumirea disciplinei", "numele disciplinei"],
    )

    cod_raw = extract_field(
        probe_text,
        patterns=[
            r"(?:codul disciplinei|cod disciplina|2\.0 cod disciplina)\s*[:\-]?\s*(?P<value>[a-z0-9._/\-]+)"
        ],
        keywords=["2.0 cod disciplina", "codul disciplinei", "cod disciplina"],
    )

    semestru_raw = extract_field(
        probe_text,
        patterns=[r"2\.5\s+semestrul\s+(?P<value>[^\n]+)"],
        keywords=["2.5 semestrul", "semestrul"],
    )
    credite_raw = extract_field(
        probe_text,
        patterns=[
            r"3\.9\s+numarul de credite[0-9\)]*\s+(?P<value>\d{1,2})",
            r"(?:numarul de credite|credite?)\s*[:\-]?\s*(?P<value>\d{1,2})",
        ],
        keywords=["3.9 numarul de credite", "numarul de credite", "credite"],
    )

    semestru = parse_semestru_token(semestru_raw)
    credite = parse_int(credite_raw)
    nume = canonicalize_course_name(nume_raw)

    # Fallbacks when regex misses.
    if not nume:
        fallback = re.search(r"2\.1 denumirea disciplinei\s+([a-z0-9 ,.'-]{5,})", norm, flags=re.IGNORECASE)
        if fallback:
            nume = canonicalize_course_name(fallback.group(1))

    cod = normalize_code(cod_raw) if cod_raw else None
    if is_auto_code(cod):
        cod = None

    return FdProbe(cod=cod, nume=nume, semestru=semestru, credite=credite)


def load_plan_rows(conn: sqlite3.Connection) -> list[PlanRow]:
    rows = conn.execute(
        """
        SELECT rowid, cod, nume, semestru, credite
        FROM plan_discipline
        ORDER BY rowid
        """
    ).fetchall()
    return [
        PlanRow(
            rowid=int(row[0]),
            cod=row[1],
            nume=canonicalize_course_name(row[2] or ""),
            semestru=row[3],
            credite=row[4],
        )
        for row in rows
    ]


def choose_best_plan_match(probe: FdProbe, plan_rows: list[PlanRow]) -> tuple[PlanRow | None, str, float]:
    if not plan_rows:
        return None, "no_plan_rows", 0.0

    probe_name = normalize_name(probe.nume)
    probe_code = normalize_code(probe.cod)

    # 1) Exact by code.
    if probe_code:
        for row in plan_rows:
            if normalize_code(row.cod) == probe_code:
                return row, "code_exact", 1.0

    # 2) Exact by normalized name.
    if probe_name:
        exact_candidates = [row for row in plan_rows if normalize_name(row.nume) == probe_name]
        if exact_candidates:
            exact_candidates.sort(
                key=lambda row: (
                    1 if probe.semestru is not None and row.semestru == probe.semestru else 0,
                    1 if probe.credite is not None and row.credite == probe.credite else 0,
                ),
                reverse=True,
            )
            return exact_candidates[0], "name_exact", 0.99

    # 3) Fuzzy by name + optional bonuses for semestru/credite.
    best_row: PlanRow | None = None
    best_score = 0.0
    for row in plan_rows:
        row_name = normalize_name(row.nume)
        ratio = SequenceMatcher(None, probe_name, row_name).ratio() if probe_name else 0.0
        if probe.semestru is not None and row.semestru == probe.semestru:
            ratio += 0.03
        if probe.credite is not None and row.credite == probe.credite:
            ratio += 0.02
        if ratio > best_score:
            best_score = ratio
            best_row = row

    if best_row and best_score >= 0.55:
        return best_row, "name_fuzzy", min(best_score, 1.0)
    return None, "no_match", best_score


def render_value(value: str | int | None) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def build_single_fd_html(plan_row: PlanRow, debug_source: str) -> str:
    title = html.escape(plan_row.nume or "disciplina")
    cod = render_value(plan_row.cod if not is_auto_code(plan_row.cod) else None) or "-"
    semestru = render_value(plan_row.semestru) or "-"
    credite = render_value(plan_row.credite) or "-"
    source = html.escape(debug_source)

    return f"""<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FD precompletata - {title}</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --page: #ffffff;
      --line: #d9e1ee;
      --line-strong: #c6d2e4;
      --text: #172033;
      --muted: #5f6c83;
      --accent: #0f5d8d;
      --chip: #0f172a;
      --filled-bg: #f1f6ff;
      --filled-txt: #0e336f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 0% 0%, #ebf8ff 0%, transparent 38%),
        radial-gradient(circle at 100% 0%, #fff1dc 0%, transparent 34%),
        linear-gradient(180deg, #f9fbff 0%, var(--bg) 65%, #edf2fa 100%);
    }}
    .wrap {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .fd-page {{
      position: relative;
      background: var(--page);
      border: 1px solid var(--line-strong);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 16px 34px rgba(18, 32, 51, 0.08);
      margin-bottom: 24px;
    }}
    .fd-band {{
      position: absolute;
      inset: 0 0 auto 0;
      height: 7px;
      border-radius: 18px 18px 0 0;
      background: linear-gradient(90deg, #0f5d8d 0%, #2d7fc7 45%, #58a7d0 100%);
    }}
    .fd-header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin: 4px 0 14px;
    }}
    .title-block h2 {{
      margin: 2px 0 4px;
      font-size: 27px;
      font-weight: 700;
      line-height: 1.12;
      color: #12243b;
      text-transform: capitalize;
    }}
    .kicker {{
      margin: 0;
      font-size: 11px;
      letter-spacing: 1.45px;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }}
    .meta-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    .chip {{
      border-radius: 999px;
      border: 1px solid var(--chip);
      background: var(--chip);
      color: #ffffff;
      padding: 5px 10px;
      font-size: 12px;
      font-weight: 700;
      line-height: 1;
    }}
    .chip-soft {{
      border-color: #c9daef;
      background: #eff6ff;
      color: #244872;
      font-weight: 600;
    }}
    .fd-table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-bottom: 12px;
      font-size: 13px;
    }}
    .fd-table th, .fd-table td {{
      border: 1px solid var(--line);
      padding: 8px 10px;
      vertical-align: top;
    }}
    .fd-table th {{
      background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
      text-align: left;
      font-weight: 700;
      color: #163d66;
    }}
    .label {{
      width: 36%;
      font-weight: 600;
      background: #fcfdff;
      color: #23344c;
    }}
    .filled {{
      background: var(--filled-bg);
      color: var(--filled-txt);
      font-weight: 600;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    @media (max-width: 920px) {{
      .fd-page {{
        border-radius: 14px;
        padding: 14px;
      }}
      .fd-band {{
        border-radius: 14px 14px 0 0;
      }}
      .fd-header {{
        flex-direction: column;
      }}
      .meta-group {{
        justify-content: flex-start;
      }}
      .title-block h2 {{
        font-size: 22px;
      }}
      .label {{
        width: 42%;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="fd-page">
      <div class="fd-band"></div>
      <div class="fd-header">
        <div class="title-block">
          <p class="kicker">FISA DISCIPLINEI</p>
          <h2>{title}</h2>
          <p class="subtitle">Cod: {cod} | Semestru: {semestru} | Credite: {credite}</p>
        </div>
        <div class="meta-group">
          <span class="chip">single</span>
          <span class="chip chip-soft">{source}</span>
        </div>
      </div>

      <table class="fd-table">
        <tr><th colspan="2">1. Date despre program</th></tr>
        <tr><td class="label">1.1 Institutia de invatamant superior</td><td></td></tr>
        <tr><td class="label">1.2 Facultatea</td><td></td></tr>
        <tr><td class="label">1.3 Departamentul</td><td></td></tr>
        <tr><td class="label">1.4 Domeniul de studii de licenta</td><td></td></tr>
        <tr><td class="label">1.5 Ciclul de studii</td><td></td></tr>
        <tr><td class="label">1.6 Programul de studii / Calificarea</td><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th colspan="2">2. Date despre disciplina</th></tr>
        <tr><td class="label">2.0 Cod disciplina</td><td class="filled">{render_value(plan_row.cod if not is_auto_code(plan_row.cod) else None)}</td></tr>
        <tr><td class="label">2.1 Denumirea disciplinei</td><td class="filled">{render_value(plan_row.nume)}</td></tr>
        <tr><td class="label">2.2 Titularul activitatilor de curs</td><td></td></tr>
        <tr><td class="label">2.3 Titularul activitatilor de seminar/laborator/proiect</td><td></td></tr>
        <tr><td class="label">2.4 Anul de studiu</td><td></td></tr>
        <tr><td class="label">2.5 Semestrul</td><td class="filled">{render_value(plan_row.semestru)}</td></tr>
        <tr><td class="label">2.6 Tipul de evaluare</td><td></td></tr>
        <tr><td class="label">2.7 Regimul disciplinei</td><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th colspan="2">3. Timpul total estimat (ore pe semestru)</th></tr>
        <tr><td class="label">3.1 Numar de ore pe saptamana</td><td></td></tr>
        <tr><td class="label">3.4 Total ore din planul de invatamant</td><td></td></tr>
        <tr><td class="label">3.8 Total ore pe semestru</td><td></td></tr>
        <tr><td class="label">3.9 Numarul de credite</td><td class="filled">{render_value(plan_row.credite)}</td></tr>
      </table>

      <table class="fd-table">
        <tr><th>4. Preconditii</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th>5. Conditii</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th>6. Competente specifice acumulate</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th>7. Obiectivele disciplinei</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th>8.1 Curs</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th>8.2 Seminar / laborator / proiect</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th>9. Coroborarea continuturilor disciplinei</th></tr>
        <tr><td></td></tr>
      </table>

      <table class="fd-table">
        <tr><th colspan="2">10. Evaluare</th></tr>
        <tr><td class="label">Tip activitate</td><td>Standarde minime de performanta</td></tr>
        <tr><td>Curs</td><td></td></tr>
        <tr><td>Seminar/Laborator</td><td></td></tr>
        <tr><td>Proiect</td><td></td></tr>
      </table>
    </section>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one FD HTML skeleton pre-filled from PI table (plan_discipline), based on a single FD PDF."
    )
    parser.add_argument("--fisa-pdf", required=True, help="Path to source FD PDF (single discipline)")
    parser.add_argument("--db-path", default="backend/data/discipline.db", help="Path to SQLite database")
    parser.add_argument(
        "--output-html",
        default="backend/compare_output/fd_single_prefilled_from_pi.html",
        help="Output HTML file path",
    )
    parser.add_argument(
        "--output-json",
        default="backend/compare_output/fd_single_prefilled_from_pi.json",
        help="Debug JSON output path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fisa_pdf_path = Path(args.fisa_pdf).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()
    output_html = Path(args.output_html).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve()

    if not fisa_pdf_path.exists():
        print(json.dumps({"status": "error", "message": "fisa_pdf_not_found", "path": str(fisa_pdf_path)}, ensure_ascii=False, indent=2))
        return 1
    if not db_path.exists():
        print(json.dumps({"status": "error", "message": "db_not_found", "path": str(db_path)}, ensure_ascii=False, indent=2))
        return 1

    raw_text = extract_text_native(fisa_pdf_path)
    probe = parse_fd_probe(raw_text)

    with sqlite3.connect(db_path) as conn:
        plan_rows = load_plan_rows(conn)

    matched, strategy, score = choose_best_plan_match(probe, plan_rows)
    if not matched:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "no_matching_disciplina_in_plan",
                    "probe": probe.__dict__,
                    "match_strategy": strategy,
                    "score": score,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    html_content = build_single_fd_html(matched, debug_source=f"PI/{strategy}")
    output_html.write_text(html_content, encoding="utf-8")

    payload = {
        "status": "success",
        "message": "single_fd_prefilled_from_pi",
        "fisa_pdf_path": str(fisa_pdf_path),
        "db_path": str(db_path),
        "match_strategy": strategy,
        "score": round(float(score), 4),
        "probe": probe.__dict__,
        "matched_plan": {
            "rowid": matched.rowid,
            "cod": matched.cod,
            "nume": matched.nume,
            "semestru": matched.semestru,
            "credite": matched.credite,
        },
        "output_html": str(output_html),
        "output_json": str(output_json),
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
