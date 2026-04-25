#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fd_migration_service import migrate_fd_pdf_to_template


DEFAULT_TEMPLATE_JSON = BACKEND_DIR / "templates" / "fd_template_v2028.json"
DEFAULT_MAPPING_JSON = BACKEND_DIR / "templates" / "fd_mapping_canonical_to_v2028.json"
DEFAULT_OUTPUT_CANONICAL = BACKEND_DIR / "compare_output" / "fd_analiza_matematica_canonical.json"
DEFAULT_OUTPUT_TEMPLATE = BACKEND_DIR / "compare_output" / "fd_analiza_matematica_template_v2028.json"
DEFAULT_OUTPUT_REPORT = BACKEND_DIR / "compare_output" / "fd_analiza_matematica_migration_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate old FD PDF to a canonical model and map it to a new template."
    )
    parser.add_argument(
        "--input-pdf",
        required=True,
        help="Path to old FD PDF",
    )
    parser.add_argument(
        "--template-json",
        default=str(DEFAULT_TEMPLATE_JSON),
        help="Path to new template skeleton JSON",
    )
    parser.add_argument(
        "--mapping-json",
        default=str(DEFAULT_MAPPING_JSON),
        help="Path to mapping JSON (canonical -> template fields)",
    )
    parser.add_argument(
        "--output-canonical-json",
        default=str(DEFAULT_OUTPUT_CANONICAL),
        help="Path to output canonical JSON",
    )
    parser.add_argument(
        "--output-template-json",
        default=str(DEFAULT_OUTPUT_TEMPLATE),
        help="Path to output migrated template JSON",
    )
    parser.add_argument(
        "--output-report-json",
        default=str(DEFAULT_OUTPUT_REPORT),
        help="Path to output migration report JSON",
    )
    parser.add_argument(
        "--scanned",
        action="store_true",
        help="Use OCR extraction for input PDF",
    )
    parser.add_argument(
        "--ocr-lang",
        default="ro,en",
        help="OCR languages used when --scanned is enabled",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_pdf = Path(args.input_pdf).expanduser().resolve()
    template_json = Path(args.template_json).expanduser().resolve()
    mapping_json = Path(args.mapping_json).expanduser().resolve()
    output_canonical = Path(args.output_canonical_json).expanduser().resolve()
    output_template = Path(args.output_template_json).expanduser().resolve()
    output_report = Path(args.output_report_json).expanduser().resolve()

    if not input_pdf.exists():
        raise FileNotFoundError(f"Missing input PDF: {input_pdf}")
    if not template_json.exists():
        raise FileNotFoundError(f"Missing template JSON: {template_json}")
    if not mapping_json.exists():
        raise FileNotFoundError(f"Missing mapping JSON: {mapping_json}")

    canonical_model, migrated_template, full_report = migrate_fd_pdf_to_template(
        input_pdf=input_pdf,
        template_json_path=template_json,
        mapping_json_path=mapping_json,
        scanned=bool(args.scanned),
        ocr_lang=args.ocr_lang,
    )

    output_canonical.parent.mkdir(parents=True, exist_ok=True)
    output_template.parent.mkdir(parents=True, exist_ok=True)
    output_report.parent.mkdir(parents=True, exist_ok=True)

    output_canonical.write_text(
        json.dumps(canonical_model, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_template.write_text(
        json.dumps(migrated_template, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_report.write_text(
        json.dumps(full_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "success",
                "canonical_output": str(output_canonical),
                "template_output": str(output_template),
                "report_output": str(output_report),
                "required_coverage": full_report["coverage_required"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
