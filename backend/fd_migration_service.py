from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fd_single_prefill_from_pi import extract_text_native, parse_fd_probe
from validator_fd import load_fd_from_input


def deep_get(container: Any, dotted_path: str) -> Any:
    if not dotted_path:
        return None
    current = container
    for segment in dotted_path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        return None
    return current


def deep_set(container: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    cursor: dict[str, Any] = container
    for segment in parts[:-1]:
        node = cursor.get(segment)
        if not isinstance(node, dict):
            node = {}
            cursor[segment] = node
        cursor = node
    cursor[parts[-1]] = value


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def resolve_source_value(canonical_model: dict[str, Any], source_spec: str) -> Any:
    if source_spec.startswith("required_fields:"):
        code = source_spec.split(":", 1)[1]
        return canonical_model.get("required_fields", {}).get(code)
    if source_spec.startswith("required_sections:"):
        code = source_spec.split(":", 1)[1]
        return canonical_model.get("required_sections", {}).get(code)
    if source_spec.startswith("distribution_hours:"):
        code = source_spec.split(":", 1)[1]
        return canonical_model.get("distribution_hours", {}).get(code)
    return deep_get(canonical_model, source_spec)


def build_canonical_model(pdf_path: Path, scanned: bool, ocr_lang: str) -> dict[str, Any]:
    parsed = load_fd_from_input(input_path=pdf_path, scanned=scanned, ocr_lang=ocr_lang)

    public_core = {
        key: value
        for key, value in parsed.items()
        if not str(key).startswith("_")
    }
    raw_text = extract_text_native(pdf_path)
    probe = parse_fd_probe(raw_text)

    disciplina = {
        "cod": probe.cod,
        "nume": public_core.get("nume_disciplina") or probe.nume,
        "semestru": public_core.get("semestru") if public_core.get("semestru") is not None else probe.semestru,
        "credite": public_core.get("credite") if public_core.get("credite") is not None else probe.credite,
    }

    return {
        "schema_version": "fd_canonical_v1",
        "source_pdf": str(pdf_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disciplina": disciplina,
        "core": public_core,
        "probe": {
            "cod": probe.cod,
            "nume": probe.nume,
            "semestru": probe.semestru,
            "credite": probe.credite,
        },
        "required_fields": parsed.get("_required_field_values", {}),
        "required_sections": parsed.get("_required_section_presence", {}),
        "distribution_hours": parsed.get("_distribution_hours", {}),
    }


def apply_mapping(
    canonical_model: dict[str, Any],
    template_payload: dict[str, Any],
    mapping_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    template_copy = copy.deepcopy(template_payload)
    mapping_entries = mapping_payload.get("mappings", [])
    if not isinstance(mapping_entries, list):
        raise ValueError("mapping file must contain a 'mappings' list")

    report_entries: list[dict[str, Any]] = []
    filled_required = 0
    missing_required: list[str] = []

    for entry in mapping_entries:
        if not isinstance(entry, dict):
            continue

        target = str(entry.get("target") or "").strip()
        source = str(entry.get("source") or "").strip()
        required = bool(entry.get("required", False))
        default = entry.get("default", None)
        if not target or not source:
            continue

        resolved = resolve_source_value(canonical_model, source)
        used_default = False
        if is_missing(resolved) and "default" in entry:
            resolved = default
            used_default = True

        deep_set(template_copy, target, resolved)

        resolved_missing = is_missing(resolved)
        if required and resolved_missing:
            missing_required.append(target)
        if required and not resolved_missing:
            filled_required += 1

        report_entries.append(
            {
                "target": target,
                "source": source,
                "required": required,
                "used_default": used_default,
                "resolved_missing": resolved_missing,
            }
        )

    required_count = sum(
        1
        for item in mapping_entries
        if isinstance(item, dict) and bool(item.get("required", False))
    )
    coverage = (filled_required / required_count) if required_count else 1.0

    report = {
        "mapping_id": mapping_payload.get("mapping_id"),
        "template_version": mapping_payload.get("template_version"),
        "required_fields_total": required_count,
        "required_fields_filled": filled_required,
        "required_fields_missing": missing_required,
        "coverage_required": round(float(coverage), 4),
        "entries": report_entries,
    }
    return template_copy, report


def load_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be object: {path}")
    return payload


def migrate_fd_pdf_to_template(
    input_pdf: Path,
    template_json_path: Path,
    mapping_json_path: Path,
    scanned: bool = False,
    ocr_lang: str = "ro,en",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    canonical_model = build_canonical_model(
        pdf_path=input_pdf,
        scanned=bool(scanned),
        ocr_lang=ocr_lang,
    )
    template_payload = load_json_file(template_json_path)
    mapping_payload = load_json_file(mapping_json_path)

    migrated_template, report = apply_mapping(
        canonical_model=canonical_model,
        template_payload=template_payload,
        mapping_payload=mapping_payload,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    if isinstance(migrated_template.get("template_meta"), dict):
        migrated_template["template_meta"]["generated_at"] = generated_at

    full_report = {
        "status": "success",
        "input_pdf": str(input_pdf),
        "template_json": str(template_json_path),
        "mapping_json": str(mapping_json_path),
        "generated_at": generated_at,
        **report,
    }

    return canonical_model, migrated_template, full_report
