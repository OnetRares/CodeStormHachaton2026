#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader


@dataclass
class PlanDisciplina:
    cod: str
    nume: str
    semestru: int
    credite: int


@dataclass(frozen=True)
class FdField:
    key: str
    label: str
    prefill_source: str | None


def remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_inline_text(text: str) -> str:
    text = remove_diacritics(text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_spelled_words(text: str) -> str:
    tokens = text.split()
    if not tokens:
        return text
    compacted: list[str] = []
    buffer: list[str] = []
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            buffer.append(token)
            continue
        if buffer:
            compacted.append("".join(buffer) if len(buffer) >= 3 else " ".join(buffer))
            buffer = []
        compacted.append(token)
    if buffer:
        compacted.append("".join(buffer) if len(buffer) >= 3 else " ".join(buffer))
    return " ".join(compacted)


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def get_fd_skeleton_fields() -> list[FdField]:
    # Canonical FD skeleton: only labels, no values pulled from template text.
    return [
        FdField("1_1", "1.1 Institutia de invatamant superior", None),
        FdField("1_2", "1.2 Facultatea", None),
        FdField("1_3", "1.3 Departamentul", None),
        FdField("1_4", "1.4 Domeniul de studii de licenta", None),
        FdField("1_5", "1.5 Ciclul de studii", None),
        FdField("1_6", "1.6 Programul de studii / Calificarea", None),
        FdField("2_0", "2.0 Cod disciplina", "cod"),
        FdField("2_1", "2.1 Denumirea disciplinei", "nume"),
        FdField("2_2", "2.2 Titularul activitatilor de curs", None),
        FdField("2_3", "2.3 Titularul activitatilor de seminar/laborator/proiect", None),
        FdField("2_4", "2.4 Anul de studiu", None),
        FdField("2_5", "2.5 Semestrul", "semestru"),
        FdField("2_6", "2.6 Tipul de evaluare", None),
        FdField("2_7", "2.7 Regimul disciplinei", None),
        FdField("3_1", "3.1 Numar de ore pe saptamana", None),
        FdField("3_4", "3.4 Total ore din planul de invatamant", None),
        FdField("3_8", "3.8 Total ore pe semestru", None),
        FdField("3_9", "3.9 Numarul de credite", "credite"),
        FdField("7_1", "7.1 Obiectivul general al disciplinei", None),
        FdField("8_1", "8.1 Curs", None),
        FdField("8_2", "8.2 Seminar/Laborator/Proiect", None),
    ]


def try_parse_plan_from_tokens(tokens: list[str]) -> PlanDisciplina | None:
    if len(tokens) < 4:
        return None

    for start_index in (0, 1):
        if start_index >= len(tokens) - 3:
            continue
        work = tokens[start_index:]
        if len(work) < 4:
            continue
        try:
            credite = int(work[-1])
            semestru = int(work[-2])
        except ValueError:
            continue

        cod = work[0].strip("()[]{}.")
        nume = " ".join(work[1:-2]).strip()

        if semestru not in (1, 2):
            continue
        if credite <= 0:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/\-]{1,24}", cod):
            continue
        if not nume:
            continue

        return PlanDisciplina(
            cod=normalize_inline_text(cod),
            nume=normalize_inline_text(nume),
            semestru=semestru,
            credite=credite,
        )
    return None


def parse_plan_from_text(plan_pdf_path: Path) -> list[PlanDisciplina]:
    raw_text = extract_pdf_text(plan_pdf_path)
    lines = [normalize_inline_text(x) for x in raw_text.splitlines() if x.strip()]
    results: list[PlanDisciplina] = []
    seen: set[tuple[str, str, int, int]] = set()

    for line in lines:
        line = line.replace("|", " ")
        line = re.sub(r"\s+", " ", line)
        if len(line) < 6 or line.startswith("total"):
            continue
        item = try_parse_plan_from_tokens(line.split(" "))
        if not item:
            continue
        item.nume = compact_spelled_words(item.nume)
        key = (item.cod, item.nume, item.semestru, item.credite)
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


_ROW_MARKER_RE = re.compile(r"^\d{1,2}(?:__?)?[_|]")


def group_words_by_line(
    words: list[dict[str, float | str]], tolerance: float = 2.0
) -> list[list[dict[str, float | str]]]:
    rows: list[list[dict[str, float | str]]] = []
    ordered = sorted(words, key=lambda w: (float(w["top"]), float(w["x0"])))
    for word in ordered:
        if not rows:
            rows.append([word])
            continue
        prev_top = float(rows[-1][0]["top"])
        current_top = float(word["top"])
        if abs(current_top - prev_top) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
    return rows


def split_line_into_segments(
    line_words: list[dict[str, float | str]]
) -> list[list[dict[str, float | str]]]:
    segments: list[list[dict[str, float | str]]] = []
    current: list[dict[str, float | str]] = []
    for word in sorted(line_words, key=lambda w: float(w["x0"])):
        token = str(word["text"])
        if _ROW_MARKER_RE.match(token) and current:
            segments.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        segments.append(current)
    return segments


def parse_segment(segment: list[dict[str, float | str]], idx: int) -> PlanDisciplina | None:
    if not segment:
        return None
    first_token = str(segment[0]["text"])
    if not _ROW_MARKER_RE.match(first_token):
        return None

    stop_tokens = {
        "df",
        "dd",
        "ds",
        "dc",
        "do",
        "dofc",
        "of",
        "oc",
        "or",
        "bc",
        "c",
        "e",
        "v",
        "fw",
        "x",
    }

    name_tokens: list[str] = []
    for word in segment:
        if float(word["x0"]) > 230.0:
            break
        token = str(word["text"]).strip("[](){}:;,.|")
        token = re.sub(r"^\d{1,2}(?:__?)?[_|]+\[?", "", token)
        token = token.strip()
        if not token:
            continue
        low = normalize_inline_text(token)
        if low in stop_tokens:
            break
        if re.fullmatch(r"\d+", low):
            continue
        if len(low) == 1 and low not in {"a", "i"}:
            continue
        name_tokens.append(token)

    if not name_tokens:
        return None
    name = compact_spelled_words(normalize_inline_text(" ".join(name_tokens)))
    if len(name) < 4:
        return None
    if "discipline cu criteriul" in name or "total ore" in name:
        return None

    credit_candidates: list[tuple[int, float]] = []
    for word in segment:
        x0 = float(word["x0"])
        if x0 < 300.0:
            continue
        token = str(word["text"])
        for n in re.findall(r"\d{1,2}", token):
            value = int(n)
            if 1 <= value <= 10:
                credit_candidates.append((value, x0))

    if credit_candidates:
        credite, credit_x = credit_candidates[-1]
    else:
        credite, credit_x = 5, 420.0
    semestru = 2 if credit_x >= 460.0 else 1

    return PlanDisciplina(
        cod=f"auto_{idx:04d}",
        nume=name,
        semestru=semestru,
        credite=credite,
    )


def parse_plan_from_layout(plan_pdf_path: Path) -> list[PlanDisciplina]:
    results: list[PlanDisciplina] = []
    seen: set[tuple[str, int, int]] = set()
    seq = 1
    with pdfplumber.open(str(plan_pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
            if not words:
                continue
            for line_words in group_words_by_line(words):
                if not any(_ROW_MARKER_RE.match(str(w["text"])) for w in line_words):
                    continue
                for segment in split_line_into_segments(line_words):
                    item = parse_segment(segment, idx=seq)
                    if not item:
                        continue
                    key = (item.nume, item.semestru, item.credite)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(item)
                    seq += 1
    return results


def render_field_row(label: str, value: str | None) -> str:
    safe_label = html.escape(label)
    safe_value = html.escape(value or "")
    css_class = "value filled" if safe_value else "value empty"
    return (
        f"<tr><td class='label'>{safe_label}</td>"
        f"<td class='{css_class}'>{safe_value}</td></tr>"
    )


def build_html(
    fd_template_pdf: Path,
    plan_pdf: Path,
    fields: list[FdField],
    disciplines: list[PlanDisciplina],
) -> str:
    empty_rows = "\n".join(render_field_row(field.label, None) for field in fields)

    sections: list[str] = []
    for idx, disciplina in enumerate(disciplines, start=1):
        rows: list[str] = []
        values = {
            "cod": disciplina.cod,
            "nume": disciplina.nume,
            "semestru": str(disciplina.semestru),
            "credite": str(disciplina.credite),
        }
        for field in fields:
            value = values.get(field.prefill_source) if field.prefill_source else None
            rows.append(render_field_row(field.label, value))
        sections.append(
            f"""
<section class="fd-card">
  <h3>FD precompletata #{idx}</h3>
  <p class="subtitle">Disciplina din PI: <strong>{html.escape(disciplina.nume)}</strong></p>
  <table>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</section>
"""
        )

    return f"""<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FD precompletata din PI</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --line: #e1e6f0;
      --text: #1b2233;
      --muted: #586178;
      --accent: #2146a2;
      --fill-bg: #eaf2ff;
      --fill-txt: #11306f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top right, #eef3ff 0%, var(--bg) 35%);
      color: var(--text);
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
    }}
    .wrap {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 20px;
    }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px 18px;
      box-shadow: 0 8px 24px rgba(27, 34, 51, 0.08);
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
    }}
    .meta {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 12px;
    }}
    .fd-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      box-shadow: 0 8px 24px rgba(27, 34, 51, 0.06);
    }}
    .fd-card h3 {{
      margin: 0 0 4px;
      font-size: 18px;
      color: var(--accent);
    }}
    .subtitle {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 13px;
    }}
    td {{
      border: 1px solid var(--line);
      padding: 8px;
      vertical-align: top;
    }}
    .label {{
      width: 45%;
      font-weight: 600;
      background: #f7f9fe;
    }}
    .value.filled {{
      background: var(--fill-bg);
      color: var(--fill-txt);
      font-weight: 700;
    }}
    .value.empty {{
      color: #9aa3b5;
      min-height: 22px;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Generare automata FD precompletata din PI (fara baza de date)</h1>
      <p class="meta">
        <strong>Template FD PDF:</strong> {html.escape(str(fd_template_pdf))}<br>
        <strong>Plan invatamant PDF:</strong> {html.escape(str(plan_pdf))}<br>
        Cimpuri completate automat din PI: <strong>cod, denumirea disciplinei, semestru, credite</strong>.<br>
        Restul cimpurilor ramin goale.
      </p>
    </section>
    <section class="fd-card">
      <h3>Schelet FD gol (model)</h3>
      <p class="subtitle">Acest bloc este varianta necompletata.</p>
      <table><tbody>{empty_rows}</tbody></table>
    </section>
    <div style="height: 12px"></div>
    <div class="grid">
      {''.join(sections)}
    </div>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read FD template PDF + PI PDF and generate HTML with empty FD skeleton + "
            "pre-filled fields from PI (without SQLite)."
        )
    )
    parser.add_argument("--fd-template-pdf", required=True, help="Path to FD template PDF")
    parser.add_argument("--plan-pdf", required=True, help="Path to plan de invatamant PDF")
    parser.add_argument(
        "--output-html",
        default="backend/compare_output/fd_prefilled_from_pi.html",
        help="Output HTML path",
    )
    parser.add_argument(
        "--output-json",
        default="backend/compare_output/fd_prefilled_from_pi.json",
        help="Optional debug JSON path with extracted data",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fd_template_pdf = Path(args.fd_template_pdf).expanduser().resolve()
    plan_pdf = Path(args.plan_pdf).expanduser().resolve()
    output_html = Path(args.output_html).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve()

    if not fd_template_pdf.exists():
        raise FileNotFoundError(f"Missing --fd-template-pdf: {fd_template_pdf}")
    if not plan_pdf.exists():
        raise FileNotFoundError(f"Missing --plan-pdf: {plan_pdf}")

    fields = get_fd_skeleton_fields()
    plan_items_text = parse_plan_from_text(plan_pdf)
    plan_items_layout = parse_plan_from_layout(plan_pdf)
    if len(plan_items_text) >= len(plan_items_layout):
        plan_items = plan_items_text
    else:
        plan_items = plan_items_layout

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    html_content = build_html(
        fd_template_pdf=fd_template_pdf,
        plan_pdf=plan_pdf,
        fields=fields,
        disciplines=plan_items,
    )
    output_html.write_text(html_content, encoding="utf-8")

    output_json.write_text(
        json.dumps(
            {
                "fd_template_pdf": str(fd_template_pdf),
                "plan_pdf": str(plan_pdf),
                "field_count": len(fields),
                "plan_discipline_count": len(plan_items),
                "fields": [field.__dict__ for field in fields],
                "disciplines": [x.__dict__ for x in plan_items],
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
                "field_count": len(fields),
                "disciplines_count": len(plan_items),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
