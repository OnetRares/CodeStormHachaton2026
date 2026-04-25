from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List


PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*%")
RE_SEM_TOKEN = re.compile(r"[^0-9iv/\-]")

FULL_REQUIRED_FIELD_PATTERNS: list[tuple[str, str, list[str]]] = [
    (
        "1.1",
        "institutia de invatamant superior",
        [
            r"1\s*\.\s*1\s+institutia\s+de\s+invatamant\s+superior\s*(?P<value>.+?)(?=1\s*\.\s*2)",
        ],
    ),
    (
        "1.2",
        "facultatea",
        [
            r"1\s*\.\s*2\s+facultatea\s*(?P<value>.+?)(?=1\s*\.\s*3)",
        ],
    ),
    (
        "1.3",
        "departamentul",
        [
            r"1\s*\.\s*3\s+departamentul\s*(?P<value>.+?)(?=1\s*\.\s*4)",
        ],
    ),
    (
        "1.4",
        "domeniul de studii",
        [
            r"1\s*\.\s*4\s+domeniul\s+de\s+studii(?:\s+de\s+licenta\d*\)?)?\s*(?P<value>.+?)(?=1\s*\.\s*5)",
        ],
    ),
    (
        "1.5",
        "ciclul de studii",
        [
            r"1\s*\.\s*5\s+ciclul\s+de\s+studii(?:\d*\)?)?\s*(?P<value>.+?)(?=1\s*\.\s*6)",
        ],
    ),
    (
        "1.6",
        "programul de studii / calificarea",
        [
            r"1\s*\.\s*6\s+programul\s+de\s+studii\s*/?\s*calificarea\s*(?P<value>.+?)(?=2\s*\.\s*1|2\s*\.\s*date\s+despre\s+disciplina)",
        ],
    ),
    (
        "2.1",
        "denumirea disciplinei",
        [
            r"2\s*\.\s*1\s+denumirea\s+disciplinei\s*(?P<value>.+?)(?=2\s*\.\s*2)",
        ],
    ),
    (
        "2.2",
        "titularul activitatilor de curs",
        [
            r"2\s*\.\s*2\s+titularul\s+activitatilor\s+de\s+curs\s*(?P<value>.+?)(?=2\s*\.\s*3)",
        ],
    ),
    (
        "2.3",
        "titularul activitatilor de seminar/laborator/proiect",
        [
            r"2\s*\.\s*3\s+titularul\s+activitatilor\s+de\s+seminar\s*/?\s*laborator\s*/?\s*proiect\s*(?P<value>.+?)(?=2\s*\.\s*4)",
            r"2\s*\.\s*3\s+titularul\s+activitatilor\s+de\s+seminar\s*/?\s*laborator\s*/?\s*(?P<value>.+?)(?=2\s*\.\s*4)",
        ],
    ),
    (
        "2.4",
        "anul de studiu",
        [
            r"2\s*\.\s*4\s+anul\s+de\s+studiu\s*(?P<value>.+?)(?=2\s*\.\s*5)",
        ],
    ),
    (
        "2.5",
        "semestrul",
        [
            r"2\s*\.\s*5\s+semestrul\s*(?P<value>.+?)(?=2\s*\.\s*6)",
        ],
    ),
    (
        "2.6",
        "tipul de evaluare",
        [
            r"2\s*\.\s*6\s+tipul\s+de\s+evaluare\s*(?P<value>.+?)(?=2\s*\.\s*7)",
        ],
    ),
    (
        "2.7",
        "regimul disciplinei",
        [
            r"2\s*\.\s*7\s+regimul\s+disciplinei\s*(?P<value>.+?)(?=3\s*\.\s*1|3\s*\.\s*timpul\s+total\s+estimat)",
            r"2\s*\.\s*7\s+regimul\s*(?P<value>.+?)(?=3\s*\.\s*1|3\s*\.\s*timpul\s+total\s+estimat)",
        ],
    ),
    (
        "3.1",
        "numar de ore pe saptamana",
        [
            r"3\s*\.\s*1\s+numar\s+de\s+ore\s+pe\s+saptamana\s*(?P<value>.+?)(?=3\s*\.\s*2)",
        ],
    ),
    (
        "3.2",
        "curs (ore/saptamana)",
        [
            r"3\s*\.\s*2\s+curs\s*(?P<value>.+?)(?=3\s*\.\s*3)",
        ],
    ),
    (
        "3.3",
        "seminar/laborator/proiect (ore/saptamana)",
        [
            r"3\s*\.\s*3\s+seminar\s*/?\s*laborator\s*/?\s*proiect\s*(?P<value>.+?)(?=3\s*\.\s*4)",
            r"3\s*\.\s*3\s+seminar\s*/?\s*laborator\s*/?\s*(?P<value>.+?)(?=3\s*\.\s*4)",
        ],
    ),
    (
        "3.4",
        "total ore din planul de invatamant",
        [
            r"3\s*\.\s*4\s+total\s+ore\s+din\s+planul\s+de\s+invatamant\s*(?P<value>.+?)(?=3\s*\.\s*5)",
        ],
    ),
    (
        "3.5",
        "curs (ore totale)",
        [
            r"3\s*\.\s*5\s+curs\s*(?P<value>.+?)(?=3\s*\.\s*6)",
        ],
    ),
    (
        "3.6",
        "seminar/laborator/proiect (ore totale)",
        [
            r"3\s*\.\s*6\s+seminar\s*/?\s*laborator\s*/?\s*proiect\s*(?P<value>.+?)(?=distributia\s+fondului\s+de\s+timp|3\s*\.\s*7)",
            r"3\s*\.\s*6\s+seminar\s*/?\s*laborator\s*/?\s*(?P<value>.+?)(?=distributia\s+fondului\s+de\s+timp|3\s*\.\s*7)",
        ],
    ),
    (
        "3.7",
        "total ore activitate student",
        [
            r"3\s*\.\s*7\s+total\s+ore(?:\s+de)?\s+activitate\s+a?\s+studentului\s*(?P<value>.+?)(?=3\s*\.\s*8)",
            r"3\s*\.\s*7\s+total\s+ore\s+studiu\s+individual\s*(?P<value>.+?)(?=3\s*\.\s*8)",
            r"3\s*\.\s*7\s+total\s+ore(?:\s+de)?\s+activitate\s+a?\s*(?P<value>.+?)(?=3\s*\.\s*8)",
        ],
    ),
    (
        "3.8",
        "total ore pe semestru",
        [
            r"3\s*\.\s*8\s+total\s+ore\s+pe\s+semestru\s*(?P<value>.+?)(?=3\s*\.\s*9)",
        ],
    ),
    (
        "3.9",
        "numarul de credite",
        [
            r"3\s*\.\s*9\s+numarul\s+de\s+credite\d*\)?\s*(?P<value>.+?)(?=4\s*\.\s*1|4\s*\.\s*preconditii)",
        ],
    ),
    (
        "4.1",
        "preconditii de curriculum",
        [
            r"4\s*\.\s*1\s+de\s+curriculum\s*(?P<value>.+?)(?=4\s*\.\s*2)",
        ],
    ),
    (
        "4.2",
        "preconditii de competente",
        [
            r"4\s*\.\s*2\s+de\s+competente\s*(?P<value>.+?)(?=5\s*\.\s*1|5\s*\.\s*conditii)",
        ],
    ),
    (
        "5.1",
        "conditii desfasurare curs",
        [
            r"5\s*\.\s*1\s+de\s+desfasurare\s+a\s+cursului\s*(?P<value>.+?)(?=5\s*\.\s*2)",
        ],
    ),
    (
        "5.2",
        "conditii desfasurare seminar/laborator/proiect",
        [
            r"5\s*\.\s*2\s+de\s+desfasurare\s+a\s+seminarului\s*/?\s*laboratorului\s*/?\s*proiectului\s*(?P<value>.+?)(?=6\s*\.\s*competente)",
            r"5\s*\.\s*2\s+de\s+desfasurare\s+a\s+seminarului\s*/?\s*(?P<value>.+?)(?=6\s*\.\s*competente)",
        ],
    ),
    (
        "7.1",
        "obiectivul general al disciplinei",
        [
            r"7\s*\.\s*1\s+obiectivul\s+general\s+al\s+disciplinei\s*(?P<value>.+?)(?=7\s*\.\s*2)",
        ],
    ),
    (
        "7.2",
        "obiectivele specifice",
        [
            r"7\s*\.\s*2\s+obiectivele\s+specifice\s*(?P<value>.+?)(?=8\s*\.\s*1|8\s*\.\s*continuturi)",
        ],
    ),
    (
        "8.1",
        "continuturi curs",
        [
            r"8\s*\.\s*1\s+curs\s*(?P<value>.+?)(?=8\s*\.\s*2)",
        ],
    ),
    (
        "8.2",
        "continuturi seminar/laborator/proiect",
        [
            r"8\s*\.\s*2\s+seminar\s*/?\s*laborator\s*/?\s*proiect\s*(?P<value>.+?)(?=9\s*\.\s*coroborarea)",
        ],
    ),
    (
        "10.4",
        "evaluare curs",
        [
            r"10\s*\.\s*4\s+curs\s*(?P<value>.+?)(?=10\s*\.\s*5)",
        ],
    ),
    (
        "10.5",
        "evaluare seminar/laborator/proiect",
        [
            r"10\s*\.\s*5\s+seminar\s*/?\s*laborator\s*/?\s*proiect\s*(?P<value>.+?)(?=10\s*\.\s*6)",
        ],
    ),
    (
        "10.6",
        "standard minim de performanta",
        [
            r"10\s*\.\s*6\s+standard\s+minim\s+de\s+performanta\s*(?P<value>.+?)(?=prezenta\s+fisa|nota\s*:|\Z)",
        ],
    ),
]

REQUIRED_SECTION_PATTERNS: list[tuple[str, str, str]] = [
    ("6", "competente specifice acumulate", r"6\s*\.\s*competente\s+specifice"),
    ("9", "coroborarea continuturilor", r"9\s*\.\s*coroborarea\s+continuturilor"),
    ("10", "evaluare", r"10\s*\.\s*evaluare"),
]

FULL_REQUIRED_FIELD_LABELS = {
    code: label for code, label, _patterns in FULL_REQUIRED_FIELD_PATTERNS
}
REQUIRED_SECTION_LABELS = {
    code: label for code, label, _pattern in REQUIRED_SECTION_PATTERNS
}

DISTRIBUTION_LINE_MARKERS: list[tuple[str, str, str]] = [
    (
        "3.df.studiu_dupa_manual",
        "distributia fondului de timp - studiul dupa manual",
        "studiul dupa manual, suport de curs, bibliografie si notite",
    ),
    (
        "3.df.documentare_suplimentara",
        "distributia fondului de timp - documentare suplimentara",
        "documentare suplimentara in biblioteca, pe platformele electronice de specialitate si pe teren",
    ),
    (
        "3.df.pregatire_seminare",
        "distributia fondului de timp - pregatire seminare/laboratoare/proiecte",
        "pregatire seminare/ laboratoare/ proiecte, teme, referate, portofolii si eseuri",
    ),
    (
        "3.df.tutoriat",
        "distributia fondului de timp - tutoriat",
        "tutoriat",
    ),
    (
        "3.df.examinari",
        "distributia fondului de timp - examinari",
        "examinari",
    ),
    (
        "3.df.alte_activitati",
        "distributia fondului de timp - alte activitati",
        "alte activitati",
    ),
]

DISTRIBUTION_REQUIRED_LABELS = {
    code: label for code, label, _marker in DISTRIBUTION_LINE_MARKERS
}


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_multiline_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = _strip_diacritics(raw_line.lower())
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _normalize_inline(text: str) -> str:
    return re.sub(r"\s+", " ", _strip_diacritics(text or "")).strip()


def _find_field(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = (match.groupdict().get("value") or "").strip()
            if value:
                return value
    return None


def _find_field_multiline(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = _normalize_inline(match.groupdict().get("value") or "")
            if value:
                return value
    return None


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    normalized = _normalize_inline(str(value))
    if not normalized:
        return False
    return bool(re.search(r"[a-z0-9]", normalized))


def _extract_required_field_values(normalized_text: str) -> dict[str, str | None]:
    extracted: dict[str, str | None] = {}
    for code, _label, patterns in FULL_REQUIRED_FIELD_PATTERNS:
        extracted[code] = _find_field_multiline(normalized_text, patterns)
    return extracted


def _extract_required_sections_presence(normalized_text: str) -> dict[str, bool]:
    presence: dict[str, bool] = {}
    for code, _label, pattern in REQUIRED_SECTION_PATTERNS:
        presence[code] = bool(re.search(pattern, normalized_text, flags=re.IGNORECASE))
    return presence


def _extract_distribution_hours(normalized_text: str) -> dict[str, int | None]:
    values: dict[str, int | None] = {}
    lines = normalized_text.splitlines()
    for code, _label, marker in DISTRIBUTION_LINE_MARKERS:
        matched_line = next((line for line in lines if line.startswith(marker)), None)
        if not matched_line:
            values[code] = None
            continue
        numbers = re.findall(r"\d+", matched_line)
        values[code] = int(numbers[-1]) if numbers else None
    return values


def _first_int(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    match = re.search(r"\d+", raw_value)
    if not match:
        return None
    return int(match.group(0))


def _sum_numbers(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    numbers = [int(x) for x in re.findall(r"\d+", raw_value)]
    if not numbers:
        return None
    return sum(numbers)


def _extract_chunk_sum(text: str, marker: str, stop_markers: list[str]) -> int | None:
    idx = text.find(marker)
    if idx < 0:
        return None

    start = idx + len(marker)
    end = len(text)
    for stop in stop_markers:
        pos = text.find(stop, start)
        if pos >= 0:
            end = min(end, pos)
    return _sum_numbers(text[start:end])


def _extract_chunk_first_int(text: str, marker: str, stop_markers: list[str]) -> int | None:
    idx = text.find(marker)
    if idx < 0:
        return None

    start = idx + len(marker)
    end = len(text)
    for stop in stop_markers:
        pos = text.find(stop, start)
        if pos >= 0:
            end = min(end, pos)
    return _first_int(text[start:end])


def _parse_semester(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    head = _normalize_inline(raw_value).split(" ", 1)[0]
    head = RE_SEM_TOKEN.sub("", head)
    if head.startswith("1") or head == "i":
        return 1
    if head.startswith("2") or head == "ii":
        return 2
    if head in {"i-ii", "i/ii"}:
        return 1
    return None


def _extract_weights_from_text(normalized_text: str) -> list[int]:
    eval_block = normalized_text
    start_idx = normalized_text.find("10. evaluare")
    if start_idx >= 0:
        block = normalized_text[start_idx:]
        stop_candidates: list[int] = []
        for marker in ("\n10.6 standard", "\n11.", "\nprezenta fisa"):
            idx = block.find(marker)
            if idx > 0:
                stop_candidates.append(idx)
        if stop_candidates:
            eval_block = block[: min(stop_candidates)]
        else:
            eval_block = block

    values: list[int] = []
    for match in PERCENT_RE.finditer(eval_block):
        value = int(match.group(1))
        if 0 <= value <= 100:
            values.append(value)
    return values


def _extract_hours(normalized_text: str) -> dict[str, int | None]:
    total_plan_34 = _first_int(
        _find_field(
            normalized_text,
            [
                r"3\.4\s+total ore(?: din planul de invatamant)?\s+(?P<value>[0-9/ ]+)",
                r"3\.4\s+total ore(?: din planul de)?\s+(?P<value>[0-9/ ]+)",
            ],
        )
    )
    if total_plan_34 is None:
        total_plan_34 = _extract_chunk_first_int(
            normalized_text,
            marker="3.4",
            stop_markers=["3.5", "3.6", "3.7", "3.8", "distributia fondului de timp"],
        )

    total_plan_38 = _first_int(
        _find_field(
            normalized_text,
            [r"3\.8\s+total ore pe semestru\s+(?P<value>[0-9/ ]+)"],
        )
    )

    # Business rule: for "curs + laborator", compare against 3.4 (plan ore didactice).
    # 3.8 is only a fallback when 3.4 cannot be extracted.
    total_plan = total_plan_34 if total_plan_34 is not None else total_plan_38

    curs_total = _first_int(_find_field(normalized_text, [r"3\.5\s+curs\s+(?P<value>[0-9/ ]+)"]))
    lab_total = _sum_numbers(
        _find_field(
            normalized_text,
            [r"3\.6\s+seminar/?\s*laborator/?\s*proiect\s+(?P<value>[0-9/ ]+)"],
        )
    )
    if lab_total is None:
        lab_total = _extract_chunk_sum(
            normalized_text,
            marker="3.6",
            stop_markers=["3.7", "3.8", "distributia fondului de timp"],
        )

    # Fallback from weekly hours (3.2 and 3.3), converted to 14 weeks.
    curs_week = _first_int(_find_field(normalized_text, [r"3\.2\s+curs\s+(?P<value>[0-9/ ]+)"]))
    lab_week = _sum_numbers(
        _find_field(
            normalized_text,
            [r"3\.3\s+seminar/?\s*laborator/?\s*proiect\s+(?P<value>[0-9/ ]+)"],
        )
    )
    if lab_week is None:
        lab_week = _extract_chunk_sum(
            normalized_text,
            marker="3.3",
            stop_markers=["3.4", "3.5", "3.6"],
        )
    curs_from_week = curs_week * 14 if curs_week is not None else None
    lab_from_week = lab_week * 14 if lab_week is not None else None

    candidate_curs = [x for x in (curs_total, curs_from_week) if x is not None]
    candidate_lab = [x for x in (lab_total, lab_from_week) if x is not None]

    chosen_curs = candidate_curs[0] if candidate_curs else None
    chosen_lab = candidate_lab[0] if candidate_lab else None

    if total_plan is not None and candidate_curs and candidate_lab:
        for c in candidate_curs:
            for l in candidate_lab:
                if c + l == total_plan:
                    chosen_curs = c
                    chosen_lab = l
                    break
            if chosen_curs + chosen_lab == total_plan:
                break

    return {
        "total_plan": total_plan,
        "curs": chosen_curs,
        "laborator": chosen_lab,
    }


def _extract_text_from_json_payload(payload: dict[str, Any]) -> str:
    full_text = payload.get("full_text")
    if isinstance(full_text, str) and full_text.strip():
        return full_text

    pages = payload.get("pages")
    if isinstance(pages, list):
        chunks: list[str] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            text = page.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text)
        if chunks:
            return "\n\n".join(chunks)

    raise ValueError("JSON does not contain full_text/pages text.")


def _build_canonical_from_text(raw_text: str) -> dict[str, Any]:
    normalized = _normalize_multiline_text(raw_text)
    required_fields = _extract_required_field_values(normalized)
    required_sections = _extract_required_sections_presence(normalized)
    distribution_hours = _extract_distribution_hours(normalized)
    discipline_name = _find_field(
        normalized,
        [
            r"2\.1\s+denumirea disciplinei\s+(?P<value>[^\n]+)",
            r"(?:numele disciplinei|denumirea disciplinei)\s*[:\-]\s*(?P<value>[^\n]+)",
        ],
    )
    semester_raw = _find_field(
        normalized,
        [
            r"2\.5\s+semestrul\s+(?P<value>[^\n ]+)",
            r"(?:semestrul|semestru)\s*[:\-]?\s*(?P<value>[iv0-9/\-]+)",
        ],
    )
    credits_raw = _find_field(
        normalized,
        [
            r"3\.9\s+numarul de credite[0-9\)]*\s+(?P<value>\d{1,2})",
            r"(?:credite?(?:\s+ects)?)\s*[:\-]?\s*(?P<value>\d{1,2})",
        ],
    )
    eval_raw = _find_field(
        normalized,
        [
            r"2\.6\s+tipul de evaluare\s+(?P<value>[a-z0-9 ]+)",
            r"(?:forma de evaluare|evaluare)\s*[:\-]\s*(?P<value>[a-z0-9 ]+)",
        ],
    )

    eval_token = (_normalize_inline(eval_raw).split(" ", 1)[0] if eval_raw else "").lower()
    eval_map = {
        "examen": "E",
        "exam": "E",
        "e": "E",
        "colocviu": "C",
        "c": "C",
        "verificare": "V",
        "v": "V",
    }
    eval_tip = eval_map.get(eval_token, eval_token[:1].upper() if eval_token else None)

    weights = _extract_weights_from_text(normalized)
    hours = _extract_hours(normalized)

    return {
        "nume_disciplina": _normalize_inline(discipline_name) if discipline_name else None,
        "semestru": _parse_semester(semester_raw),
        "credite": _first_int(credits_raw),
        "evaluare": {
            "tip": eval_tip,
            "ponderi_curs_laborator": weights,
        },
        "ore": hours,
        "_required_field_values": required_fields,
        "_required_section_presence": required_sections,
        "_distribution_hours": distribution_hours,
    }


def _attach_required_metadata(canonical: dict[str, Any], raw_text: str | None) -> dict[str, Any]:
    if not raw_text:
        return canonical
    normalized = _normalize_multiline_text(raw_text)
    canonical["_required_field_values"] = _extract_required_field_values(normalized)
    canonical["_required_section_presence"] = _extract_required_sections_presence(normalized)
    canonical["_distribution_hours"] = _extract_distribution_hours(normalized)
    return canonical


def _extract_pdf_text_fast(input_path: Path) -> str:
    import pdfplumber

    chunks: list[str] = []
    with pdfplumber.open(str(input_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
    return "\n\n".join(chunks)


def _extract_pdf_text_with_ocr(input_path: Path, ocr_lang: str) -> str:
    try:
        from pdf_ingestion_service import extract_text
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pdf_ingestion_service dependencies are missing. Install backend requirements."
        ) from exc

    return extract_text(input_path, scanned=True, ocr_lang=ocr_lang)


def load_fd_from_input(input_path: Path, scanned: bool = False, ocr_lang: str = "ro,en") -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON input must be an object")

        # Already canonical.
        if all(k in payload for k in ("nume_disciplina", "semestru", "credite", "evaluare", "ore")):
            canonical = dict(payload)
            try:
                raw_text = _extract_text_from_json_payload(payload)
            except ValueError:
                raw_text = None
            return _attach_required_metadata(canonical, raw_text)

        # Fisa-like compact shape.
        if all(k in payload for k in ("nume", "semestru", "credite")):
            canonical = {
                "nume_disciplina": payload.get("nume"),
                "semestru": payload.get("semestru"),
                "credite": payload.get("credite"),
                "evaluare": {
                    "tip": payload.get("evaluare") or payload.get("evaluare_format"),
                    "ponderi_curs_laborator": payload.get("ponderi") or [],
                },
                "ore": {
                    "total_plan": payload.get("total_ore_plan"),
                    "curs": payload.get("curs_ore_total"),
                    "laborator": payload.get("laborator_ore_total"),
                },
            }
            try:
                raw_text = _extract_text_from_json_payload(payload)
            except ValueError:
                raw_text = None
            return _attach_required_metadata(canonical, raw_text)

        raw_text = _extract_text_from_json_payload(payload)
        return _build_canonical_from_text(raw_text)

    if suffix == ".pdf":
        if scanned:
            raw_text = _extract_pdf_text_with_ocr(input_path, ocr_lang=ocr_lang)
        else:
            raw_text = _extract_pdf_text_fast(input_path)
            if not raw_text.strip():
                raw_text = _extract_pdf_text_with_ocr(input_path, ocr_lang=ocr_lang)
        return _build_canonical_from_text(raw_text)

    raise ValueError(f"Unsupported input extension: {suffix}")


class ValidatorFD:
    """Validator for `Fisa_Disciplina`-shaped dicts.

    Expects input like:
    {
      "nume_disciplina": str,
      "semestru": int,
      "credite": int,
      "evaluare": { "tip": str, "ponderi_curs_laborator": [int, ...] },
      "ore": { "total_plan": int, "curs": int, "laborator": int }
    }
    """

    def __init__(self, data: Dict[str, Any]):
        self.data = data or {}

    def check_missing_fields(self) -> List[str]:
        """Return list of keys (dot notation) that are null/empty."""
        missing: List[str] = []

        def empty(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str) and val.strip() == "":
                return True
            if isinstance(val, (list, tuple)) and len(val) == 0:
                return True
            return False

        for key in ("nume_disciplina", "semestru", "credite"):
            if empty(self.data.get(key)):
                missing.append(key)

        ev = self.data.get("evaluare")
        if not isinstance(ev, dict):
            missing.append("evaluare")
        else:
            if empty(ev.get("tip")):
                missing.append("evaluare.tip")
            if empty(ev.get("ponderi_curs_laborator")):
                missing.append("evaluare.ponderi_curs_laborator")

        ore = self.data.get("ore")
        if not isinstance(ore, dict):
            missing.append("ore")
        else:
            for sub in ("total_plan", "curs", "laborator"):
                if empty(ore.get(sub)):
                    missing.append(f"ore.{sub}")

        required_field_values = self.data.get("_required_field_values")
        if isinstance(required_field_values, dict):
            for code, label in FULL_REQUIRED_FIELD_LABELS.items():
                if not _has_meaningful_value(required_field_values.get(code)):
                    missing.append(f"{code} {label}")

        required_sections = self.data.get("_required_section_presence")
        if isinstance(required_sections, dict):
            for code, label in REQUIRED_SECTION_LABELS.items():
                if not bool(required_sections.get(code)):
                    missing.append(f"{code} {label}")

        distribution_hours = self.data.get("_distribution_hours")
        if isinstance(distribution_hours, dict):
            for code, label in DISTRIBUTION_REQUIRED_LABELS.items():
                if distribution_hours.get(code) is None:
                    missing.append(f"{code} {label}")

        return missing

    def check_math(self) -> Dict[str, str]:
        """Return dict with integrity errors found."""
        errors: Dict[str, str] = {}

        ev = self.data.get("evaluare", {})
        weights = ev.get("ponderi_curs_laborator") if isinstance(ev, dict) else None
        if not isinstance(weights, list):
            errors["ponderi"] = "evaluare.ponderi_curs_laborator is missing or not a list"
        else:
            try:
                total = sum(int(x) for x in weights)
            except Exception:
                errors["ponderi"] = "evaluare.ponderi_curs_laborator contains non-integer values"
            else:
                if total != 100:
                    errors["ponderi"] = f"sum is {total}, expected 100"

        ore = self.data.get("ore") if isinstance(self.data.get("ore"), dict) else None
        if not ore:
            errors["ore"] = "ore object missing or malformed"
        else:
            tp = ore.get("total_plan")
            c = ore.get("curs")
            l = ore.get("laborator")
            if tp is None or c is None or l is None:
                errors["ore"] = "one of ore.total_plan, ore.curs, ore.laborator is missing"
            else:
                try:
                    if int(c) + int(l) != int(tp):
                        errors["ore"] = (
                            f"curs + laborator = {int(c) + int(l)}, expected total_plan {int(tp)}"
                        )
                except Exception:
                    errors["ore"] = "ore fields contain non-integer values"

        distribution_hours = self.data.get("_distribution_hours")
        ore_obj = self.data.get("ore")
        if isinstance(distribution_hours, dict) and isinstance(ore_obj, dict):
            if all(distribution_hours.get(code) is not None for code in DISTRIBUTION_REQUIRED_LABELS):
                total_distribution = sum(int(distribution_hours[code]) for code in DISTRIBUTION_REQUIRED_LABELS)
                total_student = _first_int(
                    self.data.get("_required_field_values", {}).get("3.7")
                    if isinstance(self.data.get("_required_field_values"), dict)
                    else None
                )
                if total_student is not None and total_distribution != total_student:
                    errors["distributie_ore"] = (
                        f"sum distributie fond timp = {total_distribution}, expected 3.7 total {total_student}"
                    )

        return errors


def run_validation(fd_data: dict[str, Any]) -> dict[str, Any]:
    validator = ValidatorFD(fd_data)
    missing = validator.check_missing_fields()
    math_errors = validator.check_math()
    public_canonical = {
        key: value
        for key, value in (fd_data or {}).items()
        if not str(key).startswith("_")
    }
    return {
        "valid": not missing and not math_errors,
        "missing_fields": missing,
        "math_errors": math_errors,
        "fisa_canonical": public_canonical,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a single Fisa Disciplina file (JSON or PDF)."
    )
    parser.add_argument(
        "-i",
        "--input",
        default=None,
        help="Path to input file (.json from pdf_to_json or .pdf).",
    )
    parser.add_argument(
        "--scanned",
        action="store_true",
        help="Use OCR path for PDF input.",
    )
    parser.add_argument(
        "--ocr-lang",
        default="ro,en",
        help="OCR languages, used only with --scanned PDF.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input:
        sample = {
            "nume_disciplina": "Algoritmi",
            "semestru": 1,
            "credite": 6,
            "evaluare": {"tip": "E", "ponderi_curs_laborator": [50, 50]},
            "ore": {"total_plan": 42, "curs": 28, "laborator": 14},
        }
        print(json.dumps(run_validation(sample), ensure_ascii=False, indent=2))
        return 0

    input_path = Path(args.input).expanduser()
    try:
        canonical = load_fd_from_input(
            input_path=input_path,
            scanned=bool(args.scanned),
            ocr_lang=args.ocr_lang,
        )
        result = run_validation(canonical)
        result["input_file"] = str(input_path.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error": str(exc),
                    "input_file": str(input_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
