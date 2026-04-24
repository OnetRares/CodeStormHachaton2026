#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import HtmlDiff, SequenceMatcher
from pathlib import Path

from pypdf import PdfReader


@dataclass
class ExtractedPdf:
    source_file: str
    page_count: int
    pages: list[dict]
    full_text: str


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_compare(text: str) -> str:
    compact = normalize_whitespace(text)
    without_diacritics = "".join(
        ch for ch in unicodedata.normalize("NFKD", compact)
        if not unicodedata.combining(ch)
    )
    return without_diacritics.lower()


def extract_pdf(pdf_path: Path) -> ExtractedPdf:
    reader = PdfReader(str(pdf_path))
    pages: list[dict] = []
    full_text_parts: list[str] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": index, "text": text})
        if text.strip():
            full_text_parts.append(text.strip())

    return ExtractedPdf(
        source_file=str(pdf_path.resolve()),
        page_count=len(pages),
        pages=pages,
        full_text="\n\n".join(full_text_parts),
    )


def extracted_to_json_payload(data: ExtractedPdf) -> dict:
    return {
        "source_file": data.source_file,
        "page_count": data.page_count,
        "pages": data.pages,
        "full_text": data.full_text,
    }


def build_line_view(data: ExtractedPdf) -> list[str]:
    lines: list[str] = []
    for page in data.pages:
        page_number = page["page"]
        raw_text = page["text"] or ""
        page_lines = [normalize_whitespace(x) for x in raw_text.splitlines()]
        page_lines = [x for x in page_lines if x]
        if not page_lines:
            continue
        lines.append(f"--- PAGE {page_number} ---")
        lines.extend(page_lines)
    return lines


def build_diff_payload(left_lines: list[str], right_lines: list[str]) -> dict:
    left_cmp = [normalize_for_compare(line) for line in left_lines]
    right_cmp = [normalize_for_compare(line) for line in right_lines]
    matcher = SequenceMatcher(None, left_cmp, right_cmp)

    equal_count = 0
    replace_count = 0
    delete_count = 0
    insert_count = 0
    changes: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            equal_count += i2 - i1
            continue
        if tag == "replace":
            replace_count += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            delete_count += i2 - i1
        elif tag == "insert":
            insert_count += j2 - j1

        changes.append(
            {
                "type": tag,
                "left_range": {"start": i1, "end": i2},
                "right_range": {"start": j1, "end": j2},
                "left_lines": left_lines[i1:i2],
                "right_lines": right_lines[j1:j2],
            }
        )

    return {
        "summary": {
            "left_line_count": len(left_lines),
            "right_line_count": len(right_lines),
            "equal_lines": equal_count,
            "replaced_lines": replace_count,
            "deleted_lines": delete_count,
            "inserted_lines": insert_count,
            "similarity_ratio": round(matcher.ratio(), 4),
        },
        "changes": changes,
    }


def build_html_diff(
    left_lines: list[str],
    right_lines: list[str],
    left_label: str,
    right_label: str,
    summary: dict,
) -> str:
    html_diff = HtmlDiff(tabsize=2, wrapcolumn=120)
    table_html = html_diff.make_table(
        left_lines,
        right_lines,
        fromdesc=html.escape(left_label),
        todesc=html.escape(right_label),
        context=False,
        numlines=1,
    )

    similarity_pct = float(summary["similarity_ratio"]) * 100.0
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PDF Visual Diff</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --panel: #ffffff;
      --line: #e4e7ee;
      --text: #141821;
      --muted: #5b6476;
      --accent: #14366e;
      --danger-bg: #ffe4e6;
      --danger-text: #9f1239;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--text);
      background: linear-gradient(160deg, #eef3ff 0%, var(--bg) 35%, #fff8f8 100%);
    }}
    .shell {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 22px;
    }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px 20px;
      box-shadow: 0 8px 24px rgba(20, 24, 33, 0.08);
      margin-bottom: 14px;
    }}
    .title {{
      font-size: 24px;
      font-weight: 700;
      margin: 0 0 8px;
      letter-spacing: 0.2px;
    }}
    .meta {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}
    .cards {{
      margin: 14px 0 18px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .value {{
      font-size: 20px;
      font-weight: 700;
      color: var(--accent);
    }}
    .legend {{
      color: var(--muted);
      font-size: 13px;
      margin: 0 0 12px;
    }}
    .chip {{
      display: inline-block;
      border: 1px solid #fca5a5;
      background: var(--danger-bg);
      color: var(--danger-text);
      font-weight: 700;
      border-radius: 999px;
      padding: 2px 8px;
      margin-left: 6px;
    }}
    .diff-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: auto;
      box-shadow: 0 8px 24px rgba(20, 24, 33, 0.06);
    }}
    table.diff {{
      width: 100%;
      border-collapse: collapse;
      font-family: "IBM Plex Mono", "Consolas", monospace;
      font-size: 12px;
      line-height: 1.45;
    }}
    .diff_header {{
      background: #edf2ff;
      color: #213057;
      font-weight: 700;
      border-bottom: 1px solid var(--line);
      padding: 8px;
    }}
    td {{
      border-bottom: 1px solid #f0f2f6;
      padding: 4px 8px;
      vertical-align: top;
      word-break: break-word;
    }}
    .diff_next {{
      background: #f9fafc;
      color: #6b7280;
      text-align: center;
      font-weight: 600;
      width: 26px;
    }}
    .diff_add,
    .diff_sub,
    .diff_chg {{
      background: var(--danger-bg) !important;
      color: var(--danger-text) !important;
      font-weight: 700;
      border-radius: 3px;
      padding: 1px 2px;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1 class="title">PDF Visual Comparison</h1>
      <p class="meta"><strong>Left:</strong> {html.escape(left_label)}<br><strong>Right:</strong> {html.escape(right_label)}</p>
      <div class="cards">
        <div class="card"><span class="label">Similarity</span><span class="value">{similarity_pct:.2f}%</span></div>
        <div class="card"><span class="label">Equal Lines</span><span class="value">{int(summary["equal_lines"])}</span></div>
        <div class="card"><span class="label">Replaced</span><span class="value">{int(summary["replaced_lines"])}</span></div>
        <div class="card"><span class="label">Inserted</span><span class="value">{int(summary["inserted_lines"])}</span></div>
        <div class="card"><span class="label">Deleted</span><span class="value">{int(summary["deleted_lines"])}</span></div>
      </div>
      <p class="legend">Changes are highlighted in red.<span class="chip">MODIFIED</span></p>
    </section>
    <section class="diff-wrap">
      {table_html}
    </section>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract 2 JSON files from 2 PDFs and generate visual (HTML) line-by-line diff."
        )
    )
    parser.add_argument("--left-pdf", required=True, help="Path to first PDF")
    parser.add_argument("--right-pdf", required=True, help="Path to second PDF")
    parser.add_argument(
        "--output-dir",
        default="backend/compare_output",
        help="Output directory for generated JSON and HTML files",
    )
    parser.add_argument(
        "--left-json",
        default=None,
        help="Optional custom path for first extracted JSON",
    )
    parser.add_argument(
        "--right-json",
        default=None,
        help="Optional custom path for second extracted JSON",
    )
    parser.add_argument(
        "--diff-json",
        default=None,
        help="Optional custom path for diff JSON file",
    )
    parser.add_argument(
        "--diff-html",
        default=None,
        help="Optional custom path for visual diff HTML file",
    )
    return parser.parse_args()


def resolve_output_paths(
    args: argparse.Namespace, left_pdf: Path, right_pdf: Path
) -> tuple[Path, Path, Path, Path]:
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    left_stem = left_pdf.stem
    right_stem = right_pdf.stem
    if left_stem == right_stem:
        left_stem = f"{left_stem}_left"
        right_stem = f"{right_stem}_right"

    left_json = (
        Path(args.left_json).expanduser().resolve()
        if args.left_json
        else out_dir / f"{left_stem}.json"
    )
    right_json = (
        Path(args.right_json).expanduser().resolve()
        if args.right_json
        else out_dir / f"{right_stem}.json"
    )
    diff_json = (
        Path(args.diff_json).expanduser().resolve()
        if args.diff_json
        else out_dir / "comparison_diff.json"
    )
    diff_html = (
        Path(args.diff_html).expanduser().resolve()
        if args.diff_html
        else out_dir / "comparison_diff.html"
    )
    return left_json, right_json, diff_json, diff_html


def main() -> int:
    args = parse_args()
    left_pdf = Path(args.left_pdf).expanduser().resolve()
    right_pdf = Path(args.right_pdf).expanduser().resolve()

    if not left_pdf.exists():
        raise FileNotFoundError(f"Missing --left-pdf: {left_pdf}")
    if not right_pdf.exists():
        raise FileNotFoundError(f"Missing --right-pdf: {right_pdf}")

    left_json_path, right_json_path, diff_json_path, diff_html_path = (
        resolve_output_paths(args, left_pdf, right_pdf)
    )

    left_data = extract_pdf(left_pdf)
    right_data = extract_pdf(right_pdf)

    left_json_path.parent.mkdir(parents=True, exist_ok=True)
    right_json_path.parent.mkdir(parents=True, exist_ok=True)
    diff_json_path.parent.mkdir(parents=True, exist_ok=True)
    diff_html_path.parent.mkdir(parents=True, exist_ok=True)

    left_json_path.write_text(
        json.dumps(extracted_to_json_payload(left_data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    right_json_path.write_text(
        json.dumps(extracted_to_json_payload(right_data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    left_lines = build_line_view(left_data)
    right_lines = build_line_view(right_data)
    diff_payload = build_diff_payload(left_lines, right_lines)

    diff_json_path.write_text(
        json.dumps(
            {
                "left_json": str(left_json_path),
                "right_json": str(right_json_path),
                "left_source_pdf": str(left_pdf),
                "right_source_pdf": str(right_pdf),
                **diff_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    html_content = build_html_diff(
        left_lines,
        right_lines,
        left_label=left_pdf.name,
        right_label=right_pdf.name,
        summary=diff_payload["summary"],
    )
    diff_html_path.write_text(html_content, encoding="utf-8")

    result = {
        "status": "success",
        "left_json": str(left_json_path),
        "right_json": str(right_json_path),
        "diff_json": str(diff_json_path),
        "diff_html": str(diff_html_path),
        "summary": diff_payload["summary"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
