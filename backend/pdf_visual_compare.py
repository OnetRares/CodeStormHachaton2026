#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
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
    matcher = SequenceMatcher(None, left_lines, right_lines)

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
    left_lines: list[str], right_lines: list[str], left_label: str, right_label: str
) -> str:
    html_diff = HtmlDiff(tabsize=2, wrapcolumn=120)
    content = html_diff.make_file(
        left_lines,
        right_lines,
        fromdesc=html.escape(left_label),
        todesc=html.escape(right_label),
        context=False,
        numlines=1,
    )
    style_override = """
<style>
table.diff { width: 100%; border-collapse: collapse; font-family: Consolas, monospace; font-size: 12px; }
.diff_header { background: #f2f2f2; color: #1f1f1f; }
.diff_add, .diff_sub, .diff_chg { background: #ffd6d6 !important; color: #8b0000 !important; font-weight: 700; }
</style>
"""
    return content.replace("</head>", f"{style_override}\n</head>")


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
