#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pypdf import PdfReader


def build_output_path(input_path: Path, output_path: str | None) -> Path:
    if output_path:
        return Path(output_path).expanduser().resolve()
    return input_path.with_suffix(".json").resolve()


def extract_pdf_text(input_path: Path) -> dict:
    reader = PdfReader(str(input_path))
    pages = []
    full_text_parts = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": index, "text": text})
        if text.strip():
            full_text_parts.append(text.strip())

    return {
        "source_file": str(input_path.resolve()),
        "page_count": len(pages),
        "pages": pages,
        "full_text": "\n\n".join(full_text_parts),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract text from a PDF file and save it as JSON."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to input PDF file",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=False,
        help="Path to output JSON file (default: same name as input, .json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() != ".pdf":
        print(f"Input file is not a PDF: {input_path}", file=sys.stderr)
        return 1

    output_path = build_output_path(input_path, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        extracted = extract_pdf_text(input_path)
        output_path.write_text(
            json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # pragma: no cover
        print(f"Failed to process PDF: {exc}", file=sys.stderr)
        return 1

    print(f"JSON created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
