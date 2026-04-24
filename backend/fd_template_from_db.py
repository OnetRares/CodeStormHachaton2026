#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlanRow:
    idx: int
    cod: str | None
    nume: str
    semestru: int | None
    credite: int | None


@dataclass
class FisaRow:
    id: int
    cod: str | None
    nume: str
    semestru: int | None
    credite: int | None
    descriere: str
    curs: str


@dataclass
class RenderItem:
    cod: str | None
    nume: str
    semestru: int | None
    credite: int | None
    descriere: str
    curs: str
    sursa: str


def fix_mojibake(text: str) -> str:
    if not text:
        return ""
    replacements = (
        ("È˜", "Ș"),
        ("È™", "ș"),
        ("Èš", "Ț"),
        ("È›", "ț"),
        ("ÃŽ", "Î"),
        ("Ã®", "î"),
        ("Ã‚", "Â"),
        ("Ã¢", "â"),
        ("Ä‚", "Ă"),
        ("Äƒ", "ă"),
        ("Â", ""),
        ("â€¢", "•"),
        ("â€“", "-"),
        ("â€”", "-"),
    )
    out = text
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_name(text: str) -> str:
    text = remove_diacritics(fix_mojibake((text or "").lower()))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_spelled_words(text: str) -> str:
    text = fix_mojibake(text or "")
    tokens = text.split()
    if not tokens:
        return ""
    out: list[str] = []
    buffer_tokens: list[str] = []

    def flush() -> None:
        nonlocal buffer_tokens
        if not buffer_tokens:
            return
        if len(buffer_tokens) >= 3 and all(tok.isalpha() and len(tok) <= 2 for tok in buffer_tokens):
            out.append("".join(buffer_tokens))
        else:
            out.append(" ".join(buffer_tokens))
        buffer_tokens = []

    for tok in tokens:
        if tok.isalpha() and len(tok) <= 2:
            buffer_tokens.append(tok)
            continue
        flush()
        out.append(tok)
    flush()
    return " ".join(out)


def canonicalize_course_name(text: str) -> str:
    base = re.sub(r"\s+", " ", compact_spelled_words(text)).strip()
    squashed = re.sub(r"[^a-z0-9]+", "", remove_diacritics(base.lower()))
    aliases = {
        "algoritmifundamentali": "algoritmi fundamentali",
        "notiunifundamentaledeinformatica": "notiuni fundamentale de informatica",
        "notiunifundamentaledematematica": "notiuni fundamentale de matematica",
        "eticasiintegritateacademicai": "etica si integritate academica",
    }
    return aliases.get(squashed, base)


def clean_text_block(text: str) -> str:
    if not text:
        return ""
    text = fix_mojibake(text)
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_objective_text(descriere: str) -> str:
    cleaned = clean_text_block(descriere)
    if not cleaned:
        return ""
    lower = remove_diacritics(cleaned.lower())
    marker = "7.1 obiectivul general al disciplinei"
    idx = lower.find(marker)
    if idx >= 0:
        return cleaned[idx:].strip()
    return cleaned


def extract_competence_text(descriere: str) -> str:
    cleaned = clean_text_block(descriere)
    if not cleaned:
        return ""
    lines: list[str] = []
    for line in cleaned.splitlines():
        low = remove_diacritics(line.lower())
        if "competent" in low or low.startswith("cp ") or low.startswith("ct "):
            lines.append(line)
    return "\n".join(lines)


def load_plan_rows(conn: sqlite3.Connection) -> list[PlanRow]:
    rows = conn.execute(
        """
        SELECT cod, nume, semestru, credite
        FROM plan_discipline
        ORDER BY rowid
        """
    ).fetchall()
    items: list[PlanRow] = []
    for idx, row in enumerate(rows):
        items.append(
            PlanRow(
                idx=idx,
                cod=row[0],
                nume=canonicalize_course_name((row[1] or "").strip()),
                semestru=row[2],
                credite=row[3],
            )
        )
    return items


def load_fisa_rows(conn: sqlite3.Connection) -> list[FisaRow]:
    rows = conn.execute(
        """
        SELECT
          f.id,
          f.cod,
          f.nume,
          f.semestru,
          f.credite,
          COALESCE(MAX(CASE WHEN s.tip_sectiune='descriere' THEN s.continut END), '') AS descriere,
          COALESCE(MAX(CASE WHEN s.tip_sectiune='curs' THEN s.continut END), '') AS curs
        FROM fisa_discipline f
        LEFT JOIN fisa_sectiuni s ON s.fisa_id = f.id
        GROUP BY f.id, f.cod, f.nume, f.semestru, f.credite
        ORDER BY f.id
        """
    ).fetchall()
    items: list[FisaRow] = []
    for row in rows:
        items.append(
            FisaRow(
                id=row[0],
                cod=row[1],
                nume=canonicalize_course_name((row[2] or "").strip()),
                semestru=row[3],
                credite=row[4],
                descriere=clean_text_block(row[5] or ""),
                curs=clean_text_block(row[6] or ""),
            )
        )
    return items


def is_auto_code(code: str | None) -> bool:
    if not code:
        return True
    low = code.lower()
    return low.startswith("auto_") or low.startswith("fisa_")


def build_render_items(plan_rows: list[PlanRow], fisa_rows: list[FisaRow]) -> list[RenderItem]:
    plan_by_name: dict[str, list[PlanRow]] = {}
    for plan in plan_rows:
        key = normalize_name(plan.nume)
        plan_by_name.setdefault(key, []).append(plan)

    used_plan_ids: set[int] = set()
    items: list[RenderItem] = []

    for fisa in fisa_rows:
        key = normalize_name(fisa.nume)
        candidates = plan_by_name.get(key, [])
        chosen: PlanRow | None = None

        for candidate in candidates:
            if (
                candidate.idx not in used_plan_ids
                and fisa.semestru is not None
                and fisa.credite is not None
                and candidate.semestru == fisa.semestru
                and candidate.credite == fisa.credite
            ):
                chosen = candidate
                used_plan_ids.add(candidate.idx)
                break

        if chosen is None:
            for candidate in candidates:
                if candidate.idx not in used_plan_ids:
                    chosen = candidate
                    used_plan_ids.add(candidate.idx)
                    break

        cod_value = fisa.cod if not is_auto_code(fisa.cod) else None
        if not cod_value and chosen and not is_auto_code(chosen.cod):
            cod_value = chosen.cod

        items.append(
            RenderItem(
                cod=cod_value,
                nume=(chosen.nume if chosen else fisa.nume),
                semestru=fisa.semestru if fisa.semestru else (chosen.semestru if chosen else None),
                credite=fisa.credite if fisa.credite else (chosen.credite if chosen else None),
                descriere=fisa.descriere,
                curs=fisa.curs,
                sursa="fisa+plan" if chosen else "fisa",
            )
        )

    fisa_keys = {normalize_name(x.nume) for x in fisa_rows if x.nume}
    for plan in plan_rows:
        key = normalize_name(plan.nume)
        if key in fisa_keys:
            continue
        items.append(
            RenderItem(
                cod=plan.cod if not is_auto_code(plan.cod) else None,
                nume=plan.nume,
                semestru=plan.semestru,
                credite=plan.credite,
                descriere="",
                curs="",
                sursa="plan",
            )
        )

    unique_items: list[RenderItem] = []
    seen: set[tuple[str, int | None, int | None]] = set()
    for item in items:
        key = (normalize_name(item.nume), item.semestru, item.credite)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items


def html_multiline(text: str) -> str:
    if not text:
        return ""
    return "<br>".join(html.escape(line) for line in text.splitlines())


def render_value(value: str | int | None) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def render_fd_page(item: RenderItem, idx: int) -> str:
    obj_text = extract_objective_text(item.descriere)
    comp_text = extract_competence_text(item.descriere)
    title = html.escape(item.nume or f"Disciplina {idx}")
    cod = render_value(item.cod) or "-"
    semestru = render_value(item.semestru) or "-"
    credite = render_value(item.credite) or "-"
    sursa = html.escape(item.sursa)
    return f"""
<section class="fd-page">
  <div class="fd-band"></div>
  <div class="fd-header">
    <div class="title-block">
      <p class="kicker">FISA DISCIPLINEI</p>
      <h2>{title}</h2>
      <p class="subtitle">Cod: {cod} | Semestru: {semestru} | Credite: {credite}</p>
    </div>
    <div class="meta-group">
      <span class="chip">#{idx}</span>
      <span class="chip chip-soft">{sursa}</span>
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
    <tr><td class="label">2.0 Cod disciplina</td><td class="filled">{render_value(item.cod)}</td></tr>
    <tr><td class="label">2.1 Denumirea disciplinei</td><td class="filled">{render_value(item.nume)}</td></tr>
    <tr><td class="label">2.2 Titularul activitatilor de curs</td><td></td></tr>
    <tr><td class="label">2.3 Titularul activitatilor de seminar/laborator/proiect</td><td></td></tr>
    <tr><td class="label">2.4 Anul de studiu</td><td></td></tr>
    <tr><td class="label">2.5 Semestrul</td><td class="filled">{render_value(item.semestru)}</td></tr>
    <tr><td class="label">2.6 Tipul de evaluare</td><td></td></tr>
    <tr><td class="label">2.7 Regimul disciplinei</td><td></td></tr>
  </table>

  <table class="fd-table">
    <tr><th colspan="2">3. Timpul total estimat (ore pe semestru)</th></tr>
    <tr><td class="label">3.1 Numar de ore pe saptamana</td><td></td></tr>
    <tr><td class="label">3.4 Total ore din planul de invatamant</td><td></td></tr>
    <tr><td class="label">3.8 Total ore pe semestru</td><td></td></tr>
    <tr><td class="label">3.9 Numarul de credite</td><td class="filled">{render_value(item.credite)}</td></tr>
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
    <tr><td class="filled">{html_multiline(comp_text)}</td></tr>
  </table>

  <table class="fd-table">
    <tr><th>7. Obiectivele disciplinei</th></tr>
    <tr><td class="filled">{html_multiline(obj_text)}</td></tr>
  </table>

  <table class="fd-table">
    <tr><th>8.1 Curs</th></tr>
    <tr><td class="filled">{html_multiline(item.curs)}</td></tr>
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
"""


def build_html(items: list[RenderItem]) -> str:
    pages = "".join(render_fd_page(item, idx + 1) for idx, item in enumerate(items))
    return f"""<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FD precompletata</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&family=Fraunces:opsz,wght@9..144,600&display=swap');
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
      font-family: "Manrope", "Segoe UI", "Trebuchet MS", sans-serif;
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
      page-break-after: always;
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
      font-family: "Fraunces", Georgia, serif;
      font-size: 27px;
      font-weight: 600;
      line-height: 1.12;
      letter-spacing: 0.2px;
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
    @media print {{
      body {{
        background: #ffffff;
      }}
      .wrap {{
        max-width: none;
        padding: 0;
      }}
      .fd-page {{
        box-shadow: none;
        border-radius: 0;
        border: 1px solid #aab6c8;
        margin: 0 0 12px;
        page-break-after: always;
      }}
      .fd-band {{
        display: none;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    {pages}
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate full FD HTML template (all sections/tables) pre-filled from SQLite DB."
    )
    parser.add_argument(
        "--db-path",
        default="backend/data/discipline.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--output-html",
        default="backend/compare_output/fd_full_from_db.html",
        help="Output HTML file path",
    )
    parser.add_argument(
        "--output-json",
        default="backend/compare_output/fd_full_from_db.json",
        help="Debug JSON output path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser().resolve()
    output_html = Path(args.output_html).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve()

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        plan_rows = load_plan_rows(conn)
        fisa_rows = load_fisa_rows(conn)

    items = build_render_items(plan_rows, fisa_rows)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    output_html.write_text(build_html(items), encoding="utf-8")
    output_json.write_text(
        json.dumps(
            {
                "db_path": str(db_path),
                "plan_count": len(plan_rows),
                "fisa_count": len(fisa_rows),
                "render_count": len(items),
                "items": [item.__dict__ for item in items],
                "output_html": str(output_html),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "success",
                "output_html": str(output_html),
                "output_json": str(output_json),
                "render_count": len(items),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
