#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import easyocr
import fitz
import numpy as np
import pdfplumber
from PIL import Image


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("Validation failed")
        self.errors = errors


@dataclass
class FisaData:
    cod: str | None
    nume: str
    semestru: int
    credite: int
    evaluare: str
    evaluare_cod: str | None
    ponderi: list[int]
    ore_saptamana: int | None
    total_ore_plan: int | None
    continut_descriere: str
    continut_curs: str
    continut_evaluare: str


@dataclass
class PlanDisciplina:
    cod: str
    nume: str
    semestru: int
    credite: int


_EASYOCR_READERS: dict[tuple[str, ...], easyocr.Reader] = {}
_EASYOCR_MODEL_DIR = (Path(__file__).resolve().parent / ".easyocr_models").resolve()
_PLAN_ROW_MARKER_RE = re.compile(r"^\d{1,2}(?:__?)?[_|]")
_PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*%")


def remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_inline_text(text: str) -> str:
    text = remove_diacritics(text.lower())
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_multiline_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = remove_diacritics(raw_line.lower())
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


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
            if len(buffer) >= 3:
                compacted.append("".join(buffer))
            else:
                compacted.extend(buffer)
            buffer = []
        compacted.append(token)
    if buffer:
        if len(buffer) >= 3:
            compacted.append("".join(buffer))
        else:
            compacted.extend(buffer)
    return " ".join(compacted)


def normalize_evaluare(value: str) -> str:
    clean = normalize_inline_text(value)
    first_token = clean.split(" ", 1)[0] if clean else ""
    mapping = {
        "e": "examen",
        "examen": "examen",
        "exam": "examen",
        "c": "colocviu",
        "colocviu": "colocviu",
        "v": "verificare",
        "verificare": "verificare",
    }
    return mapping.get(first_token, clean)


def evaluare_to_code(normalized: str) -> str | None:
    if not normalized:
        return None
    head = normalized.split(" ", 1)[0]
    short_map = {
        "examen": "E",
        "exam": "E",
        "e": "E",
        "colocviu": "C",
        "c": "C",
        "verificare": "V",
        "v": "V",
    }
    return short_map.get(head, head[:1].upper() if head else None)


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    return int(match.group(0))


def extract_weight_values(text: str) -> list[int]:
    if not text:
        return []
    values: list[int] = []
    for match in _PERCENT_RE.finditer(text):
        try:
            value = int(match.group(1))
        except Exception:
            continue
        if 0 <= value <= 100:
            values.append(value)
    return values


def infer_evaluation_content(block_text: str) -> str:
    normalized = normalize_multiline_text(block_text)

    section = extract_section(
        normalized,
        start_keywords=[
            "10. evaluare",
            "11. evaluare",
            "evaluare",
            "forma de evaluare",
            "criterii de evaluare",
            "ponder",
            "ponderi",
        ],
        stop_keywords=[
            "bibliografie",
            "resurse",
            "anexa",
            "observatii",
        ],
    )
    if section and "%" in section:
        return section

    # Fallback: capture lines that look like evaluation/weights statements.
    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "%" in lower or "ponder" in lower or "evaluare" in lower:
            lines.append(line)

    return "\n".join(lines).strip()


def parse_semestru_token(raw_value: str) -> int | None:
    value = normalize_inline_text(raw_value)
    if not value:
        return None
    head = value.split(" ", 1)[0]
    head = re.sub(r"[^0-9iv/\-]", "", head)
    if not head:
        return None

    if head.startswith("1"):
        return 1
    if head.startswith("2"):
        return 2
    if head in {"i-ii", "i/ii"}:
        return 1
    if head == "ii":
        return 2
    if head == "i":
        return 1
    return None


def parse_semestru_from_block(text: str) -> int:
    direct_match = re.search(
        r"2\.5\s+semestrul\s+(?P<value>[^\n]+)", text, flags=re.IGNORECASE
    )
    if direct_match:
        parsed = parse_semestru_token(direct_match.group("value"))
        if parsed in (1, 2):
            return parsed

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "2.5 semestrul" not in line:
            continue
        candidate = line.split("2.5 semestrul", 1)[1].strip(" :-\t")
        if not candidate and index + 1 < len(lines):
            candidate = lines[index + 1].strip(" :-\t")
        parsed = parse_semestru_token(candidate)
        if parsed in (1, 2):
            return parsed
    return -1


def parse_ocr_languages(ocr_lang: str) -> list[str]:
    tokens = re.split(r"[,+\s]+", ocr_lang.strip())
    alias_map = {
        "ron": "ro",
        "romanian": "ro",
        "romana": "ro",
        "eng": "en",
        "english": "en",
    }
    languages: list[str] = []
    for token in tokens:
        clean = token.strip().lower()
        if not clean:
            continue
        mapped = alias_map.get(clean, clean)
        if mapped not in languages:
            languages.append(mapped)
    if not languages:
        return ["ro", "en"]
    return languages


def get_easyocr_reader(ocr_lang: str) -> easyocr.Reader:
    languages = tuple(parse_ocr_languages(ocr_lang))
    reader = _EASYOCR_READERS.get(languages)
    if reader:
        return reader

    try:
        _EASYOCR_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        reader = easyocr.Reader(
            list(languages),
            gpu=False,
            verbose=False,
            model_storage_directory=str(_EASYOCR_MODEL_DIR),
            user_network_directory=str(_EASYOCR_MODEL_DIR),
            download_enabled=True,
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            f"EasyOCR initialization failed for languages={list(languages)}: {exc}"
        ) from exc
    _EASYOCR_READERS[languages] = reader
    return reader


def extract_text_native(pdf_path: Path) -> str:
    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def extract_text_ocr(pdf_path: Path, ocr_lang: str) -> str:
    reader = get_easyocr_reader(ocr_lang=ocr_lang)
    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            mode = "RGB" if pix.n >= 3 else "L"
            image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            rgb_image = image.convert("RGB")
            np_image = np.array(rgb_image)
            lines = reader.readtext(np_image, detail=0, paragraph=True)
            parts.append("\n".join(line.strip() for line in lines if line.strip()))
    return "\n".join(parts)


def extract_text(pdf_path: Path, scanned: bool, ocr_lang: str) -> str:
    if scanned:
        return extract_text_ocr(pdf_path, ocr_lang=ocr_lang)
    return extract_text_native(pdf_path)


def extract_field(text: str, patterns: list[str], keywords: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group("value").strip(" :-\t")
            if value:
                return value

    lines = text.splitlines()
    for index, line in enumerate(lines):
        for keyword in keywords:
            if keyword not in line:
                continue
            after_keyword = line.split(keyword, 1)[1].strip(" :-\t")
            if after_keyword:
                return after_keyword
            for look_ahead in range(index + 1, min(index + 5, len(lines))):
                candidate = lines[look_ahead].strip(" :-\t")
                if candidate:
                    return candidate
    return ""


def extract_section(
    text: str, start_keywords: list[str], stop_keywords: list[str]
) -> str:
    lines = text.splitlines()
    start_idx: int | None = None
    start_keyword_used = ""

    for i, line in enumerate(lines):
        for keyword in start_keywords:
            if keyword in line:
                start_idx = i
                start_keyword_used = keyword
                break
        if start_idx is not None:
            break

    if start_idx is None:
        return ""

    collected: list[str] = []
    first_line = lines[start_idx]
    inline_value = first_line.split(start_keyword_used, 1)[1].strip(" :-\t")
    if inline_value:
        collected.append(inline_value)

    for i in range(start_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if any(line.startswith(stop_word) for stop_word in stop_keywords):
            break
        collected.append(line)

    return "\n".join(collected).strip()


def split_fisa_blocks(text: str) -> list[str]:
    normalized = normalize_multiline_text(text)
    lines = normalized.splitlines()
    marker_indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith("2.1 denumirea disciplinei")
    ]
    if not marker_indexes:
        return [normalized] if normalized.strip() else []

    blocks: list[str] = []
    for idx, start in enumerate(marker_indexes):
        end = marker_indexes[idx + 1] if idx + 1 < len(marker_indexes) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            blocks.append(block)
    return blocks


def parse_fisa(text: str) -> FisaData:
    normalized = normalize_multiline_text(text)

    nume_raw = extract_field(
        normalized,
        patterns=[
            r"2\.1\s+denumirea disciplinei\s+(?P<value>[^\n]+)",
            r"(?:numele disciplinei|nume disciplina|denumirea disciplinei)\s*[:\-]\s*(?P<value>[^\n]+)",
        ],
        keywords=["2.1 denumirea disciplinei", "numele disciplinei", "denumirea disciplinei"],
    )
    cod_raw = extract_field(
        normalized,
        patterns=[
            r"(?:codul disciplinei|cod disciplina)\s*[:\-]?\s*(?P<value>[a-z0-9._/\-]+)"
        ],
        keywords=["codul disciplinei", "cod disciplina"],
    )
    semestru = parse_semestru_from_block(normalized)
    credite_raw = extract_field(
        normalized,
        patterns=[
            r"3\.9\s+numarul de credite[0-9\)]*\s+(?P<value>\d{1,2})",
            r"(?:credite?(?:\s+ects)?)\s*[:\-]?\s*(?P<value>\d{1,2})",
        ],
        keywords=["3.9 numarul de credite", "numarul de credite", "credite"],
    )
    evaluare_raw = extract_field(
        normalized,
        patterns=[
            r"2\.6\s+tipul de evaluare\s+(?P<value>[a-z0-9 ]+)",
            r"(?:forma de evaluare|evaluare)\s*[:\-]\s*(?P<value>[a-z0-9 ]+)",
        ],
        keywords=["2.6 tipul de evaluare", "forma de evaluare", "evaluare"],
    )

    ore_saptamana_raw = extract_field(
        normalized,
        patterns=[
            r"(?:numar de ore pe saptamana|ore pe saptamana|ore/saptamana)\s*[:\-]?\s*(?P<value>\d{1,2})",
            r"(?:ore pe saptamana)\s*(?P<value>\d{1,2})",
        ],
        keywords=["ore pe saptamana", "ore/saptamana"],
    )

    total_ore_raw = extract_field(
        normalized,
        patterns=[
            r"(?:total ore|total ore din planul de invatamant|total ore plan)\s*[:\-]?\s*(?P<value>\d{1,4})",
            r"(?:total ore)\s*(?P<value>\d{1,4})",
        ],
        keywords=["total ore", "total ore din planul de invatamant"],
    )

    descriere = extract_section(
        normalized,
        start_keywords=[
            "7. obiectivele disciplinei",
            "7.1 obiectivul general al disciplinei",
            "descrierea disciplinei",
            "descriere",
        ],
        stop_keywords=[
            "8. continuturi",
            "8.1 curs",
            "8.2 seminar",
            "8.2 laborator",
            "8.2 proiect",
        ],
    )
    if not descriere:
        descriere = extract_section(
            normalized,
            start_keywords=["descriere", "descriere continut"],
            stop_keywords=["continut", "continuturi", "bibliografie", "evaluare"],
        )

    curs = extract_section(
        normalized,
        start_keywords=[
            "8.1 curs",
            "continut curs",
            "continuturi curs",
            "8. continuturi",
        ],
        stop_keywords=[
            "8.2 seminar",
            "8.2 laborator",
            "8.2 proiect",
            "bibliografie",
            "9. coroborarea",
        ],
    )
    if not curs:
        curs = extract_section(
            normalized,
            start_keywords=["continut", "tematica curs"],
            stop_keywords=["seminar", "laborator", "proiect", "bibliografie"],
        )

    cod_normalized = normalize_inline_text(cod_raw) if cod_raw else None
    if cod_normalized and len(cod_normalized) > 30:
        cod_normalized = None

    descriere_norm = normalize_multiline_text(descriere)
    curs_norm = normalize_multiline_text(curs)
    if not descriere_norm:
        descriere_norm = normalize_multiline_text(normalized[:2000])
    if not curs_norm:
        curs_norm = descriere_norm

    evaluare = normalize_evaluare(evaluare_raw) or "neprecizat"
    evaluare_cod = evaluare_to_code(evaluare)
    continut_evaluare = infer_evaluation_content(normalized)
    ponderi = extract_weight_values(continut_evaluare)
    if not ponderi:
        ponderi = extract_weight_values(normalized)
    ore_saptamana = parse_int(ore_saptamana_raw) or None
    total_ore_plan = parse_int(total_ore_raw) or None

    return FisaData(
        cod=cod_normalized,
        nume=compact_spelled_words(normalize_inline_text(nume_raw)),
        semestru=semestru,
        credite=parse_int(credite_raw) or -1,
        evaluare=evaluare,
        evaluare_cod=evaluare_cod,
        ponderi=ponderi,
        ore_saptamana=ore_saptamana,
        total_ore_plan=total_ore_plan,
        continut_descriere=descriere_norm,
        continut_curs=curs_norm,
        continut_evaluare=continut_evaluare,
    )


def parse_fise(text: str) -> list[FisaData]:
    blocks = split_fisa_blocks(text)
    if not blocks:
        return [parse_fisa(text)] if text.strip() else []

    results: list[FisaData] = []
    seen: set[tuple[str, int, int]] = set()
    for block in blocks:
        data = parse_fisa(block)
        if not data.nume:
            continue
        key = (data.nume, data.semestru, data.credite)
        if key in seen:
            continue
        seen.add(key)
        results.append(data)
    return results


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
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/\-]{1,19}", cod):
            continue
        if not nume or nume in {"nume", "disciplina", "nume disciplina"}:
            continue
        if nume.startswith("cod "):
            continue

        return PlanDisciplina(
            cod=normalize_inline_text(cod),
            nume=normalize_inline_text(nume),
            semestru=semestru,
            credite=credite,
        )

    return None


def parse_plan(text: str) -> list[PlanDisciplina]:
    normalized = normalize_multiline_text(text)
    results: list[PlanDisciplina] = []
    seen: set[tuple[str, str, int, int]] = set()

    for raw_line in normalized.splitlines():
        line = raw_line.replace("|", " ")
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 6:
            continue
        if line.startswith("total"):
            continue
        tokens = line.split(" ")
        item = try_parse_plan_from_tokens(tokens)
        if not item:
            continue
        key = (item.cod, item.nume, item.semestru, item.credite)
        if key in seen:
            continue
        seen.add(key)
        results.append(item)

    return results


def group_words_by_line(
    words: list[dict[str, float | str]], tolerance: float = 2.0
) -> list[list[dict[str, float | str]]]:
    rows: list[list[dict[str, float | str]]] = []
    ordered = sorted(words, key=lambda w: (float(w["top"]), float(w["x0"])))
    for word in ordered:
        if not rows:
            rows.append([word])
            continue
        previous_top = float(rows[-1][0]["top"])
        current_top = float(word["top"])
        if abs(current_top - previous_top) <= tolerance:
            rows[-1].append(word)
            continue
        rows.append([word])
    return rows


def clean_plan_token(token: str) -> str:
    token = re.sub(r"^\d{1,2}(?:__?)?[_|]+\[?", "", token.strip())
    token = token.strip("[](){}:;,.|")
    token = re.sub(r"\s+", " ", token)
    return token.strip()


def split_line_into_plan_segments(
    line_words: list[dict[str, float | str]]
) -> list[list[dict[str, float | str]]]:
    segments: list[list[dict[str, float | str]]] = []
    current: list[dict[str, float | str]] = []
    for word in sorted(line_words, key=lambda w: float(w["x0"])):
        text = str(word["text"])
        if _PLAN_ROW_MARKER_RE.match(text) and current:
            segments.append(current)
            current = [word]
            continue
        current.append(word)
    if current:
        segments.append(current)
    return segments


def parse_plan_segment(
    segment: list[dict[str, float | str]], sequence: int
) -> PlanDisciplina | None:
    if not segment:
        return None

    first_token = str(segment[0]["text"])
    if not _PLAN_ROW_MARKER_RE.match(first_token):
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
        token = clean_plan_token(str(word["text"]))
        if not token:
            continue
        lower = token.lower()
        if lower in stop_tokens:
            break
        if re.fullmatch(r"\d+", lower):
            continue
        if len(lower) == 1 and lower not in {"a", "i"}:
            continue
        name_tokens.append(token)

    if not name_tokens:
        return None

    name = normalize_inline_text(" ".join(name_tokens))
    if len(name) < 4:
        return None
    if any(
        blocked in name
        for blocked in (
            "semestrul",
            "total ore",
            "disciplines cu criteriul",
            "discipline cu criteriul",
            "legends",
            "legenda",
        )
    ):
        return None

    credit_candidates: list[tuple[int, float]] = []
    for word in segment:
        word_text = str(word["text"])
        word_x = float(word["x0"])
        if word_x < 300.0:
            continue
        for raw_number in re.findall(r"\d{1,2}", word_text):
            value = int(raw_number)
            if 1 <= value <= 10:
                credit_candidates.append((value, word_x))

    if credit_candidates:
        credite, credit_x = credit_candidates[-1]
    else:
        credite, credit_x = 5, 420.0

    semestru = 2 if credit_x >= 460.0 else 1
    cod = f"auto_{sequence:04d}"
    return PlanDisciplina(
        cod=cod,
        nume=name,
        semestru=semestru,
        credite=credite,
    )


def parse_plan_from_pdf_layout(plan_pdf_path: Path) -> list[PlanDisciplina]:
    results: list[PlanDisciplina] = []
    seen: set[tuple[str, int, int]] = set()
    sequence = 1

    with pdfplumber.open(str(plan_pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
            if not words:
                continue
            for line_words in group_words_by_line(words):
                if not any(
                    _PLAN_ROW_MARKER_RE.match(str(word["text"])) for word in line_words
                ):
                    continue
                for segment in split_line_into_plan_segments(line_words):
                    item = parse_plan_segment(segment, sequence=sequence)
                    if not item:
                        continue
                    key = (item.nume, item.semestru, item.credite)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(item)
                    sequence += 1

    return results


def build_plan_from_fise(fise_items: list[FisaData]) -> list[PlanDisciplina]:
    results: list[PlanDisciplina] = []
    seen: set[tuple[str, int, int]] = set()
    sequence = 1
    for item in fise_items:
        key = (item.nume, item.semestru, item.credite)
        if key in seen:
            continue
        seen.add(key)
        cod = item.cod if item.cod else f"fisa_{sequence:04d}"
        sequence += 1
        results.append(
            PlanDisciplina(
                cod=cod,
                nume=item.nume,
                semestru=item.semestru,
                credite=item.credite,
            )
        )
    return results


def validate_fisa(data: FisaData, prefix: str = "fisa") -> list[str]:
    errors: list[str] = []
    if not data.nume:
        errors.append(f"{prefix}.nume is required")
    if data.semestru not in (1, 2):
        errors.append(f"{prefix}.semestru must be 1 or 2")
    if data.credite <= 0:
        errors.append(f"{prefix}.credite must be int > 0")
    if not data.evaluare:
        errors.append(f"{prefix}.evaluare is required")
    if not data.continut_descriere:
        errors.append(f"{prefix}.continut.descriere is required")
    if not data.continut_curs:
        errors.append(f"{prefix}.continut.curs is required")
    return errors


def validate_fise(items: list[FisaData]) -> list[str]:
    errors: list[str] = []
    if not items:
        errors.append("fisa must contain at least one disciplina")
        return errors

    for index, item in enumerate(items):
        errors.extend(validate_fisa(item, prefix=f"fisa[{index}]"))
    return errors


def validate_plan(items: list[PlanDisciplina]) -> list[str]:
    errors: list[str] = []
    if not items:
        errors.append("plan must contain at least one disciplina")
        return errors

    for index, item in enumerate(items):
        if not item.cod:
            errors.append(f"plan[{index}].cod is required")
        if not item.nume:
            errors.append(f"plan[{index}].nume is required")
        if item.semestru not in (1, 2):
            errors.append(f"plan[{index}].semestru must be 1 or 2")
        if item.credite <= 0:
            errors.append(f"plan[{index}].credite must be int > 0")
    return errors


def initialize_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_discipline (
                cod TEXT NOT NULL,
                nume TEXT NOT NULL,
                semestru INTEGER NOT NULL CHECK (semestru IN (1, 2)),
                credite INTEGER NOT NULL CHECK (credite > 0)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fisa_discipline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cod TEXT,
                nume TEXT NOT NULL,
                semestru INTEGER NOT NULL CHECK (semestru IN (1, 2)),
                credite INTEGER NOT NULL CHECK (credite > 0)
                ,evaluare_format TEXT
                ,ponderi_json TEXT
                ,ore_saptamana INTEGER
                ,total_ore_plan INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fisa_sectiuni (
                fisa_id INTEGER NOT NULL,
                tip_sectiune TEXT NOT NULL,
                continut TEXT NOT NULL,
                FOREIGN KEY (fisa_id) REFERENCES fisa_discipline(id)
            )
            """
        )

        # Backward compatibility for DBs created before new columns existed.
        fisa_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info('fisa_discipline')").fetchall()}
        if "evaluare_format" not in fisa_cols:
            conn.execute("ALTER TABLE fisa_discipline ADD COLUMN evaluare_format TEXT")
        if "ponderi_json" not in fisa_cols:
            conn.execute("ALTER TABLE fisa_discipline ADD COLUMN ponderi_json TEXT")
        if "ore_saptamana" not in fisa_cols:
            conn.execute("ALTER TABLE fisa_discipline ADD COLUMN ore_saptamana INTEGER")
        if "total_ore_plan" not in fisa_cols:
            conn.execute("ALTER TABLE fisa_discipline ADD COLUMN total_ore_plan INTEGER")


def store_data(
    db_path: Path, fise_items: list[FisaData], plan_items: list[PlanDisciplina]
) -> list[int]:
    initialize_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        # Keep one consistent snapshot per run and avoid duplicates across reruns.
        conn.execute("DELETE FROM fisa_sectiuni")
        conn.execute("DELETE FROM fisa_discipline")
        conn.execute("DELETE FROM plan_discipline")

        conn.executemany(
            """
            INSERT INTO plan_discipline (cod, nume, semestru, credite)
            VALUES (?, ?, ?, ?)
            """,
            [(x.cod, x.nume, x.semestru, x.credite) for x in plan_items],
        )
        fisa_ids: list[int] = []
        for fisa in fise_items:
            cursor = conn.execute(
                """
                    INSERT INTO fisa_discipline (
                        cod,
                        nume,
                        semestru,
                        credite,
                        evaluare_format,
                        ponderi_json,
                        ore_saptamana,
                        total_ore_plan
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fisa.cod,
                        fisa.nume,
                        fisa.semestru,
                        fisa.credite,
                        fisa.evaluare_cod,
                        json.dumps(fisa.ponderi, ensure_ascii=False),
                        fisa.ore_saptamana,
                        fisa.total_ore_plan,
                    ),
            )
            fisa_id = int(cursor.lastrowid)
            fisa_ids.append(fisa_id)
            conn.executemany(
                """
                INSERT INTO fisa_sectiuni (fisa_id, tip_sectiune, continut)
                VALUES (?, ?, ?)
                """,
                [
                    (fisa_id, "descriere", fisa.continut_descriere),
                    (fisa_id, "curs", fisa.continut_curs),
                    (
                        fisa_id,
                        "evaluare",
                        fisa.continut_evaluare
                        if fisa.continut_evaluare
                        else (f"Ponderi extrase: {', '.join(str(x) for x in fisa.ponderi)}" if fisa.ponderi else ""),
                    ),
                ],
            )
        conn.commit()
    return fisa_ids


def run_pipeline(
    fisa_pdf_path: Path,
    plan_pdf_path: Path,
    is_fisa_scanned: bool,
    is_plan_scanned: bool,
    db_path: Path,
    ocr_lang: str = "ro,en",
) -> dict:
    fisa_text = extract_text(fisa_pdf_path, scanned=is_fisa_scanned, ocr_lang=ocr_lang)
    plan_text = extract_text(plan_pdf_path, scanned=is_plan_scanned, ocr_lang=ocr_lang)

    fise_items = parse_fise(fisa_text)
    plan_items = parse_plan(plan_text)
    if not plan_items:
        plan_items = parse_plan_from_pdf_layout(plan_pdf_path)
    fallback_plan = build_plan_from_fise(fise_items)
    if len(plan_items) < len(fallback_plan):
        plan_items = fallback_plan

    errors = validate_fise(fise_items) + validate_plan(plan_items)
    if errors:
        raise ValidationError(errors)

    fisa_ids = store_data(
        db_path=db_path, fise_items=fise_items, plan_items=plan_items
    )

    return {
        "status": "success",
        "message": "pdf processed and stored",
        "db_path": str(db_path.resolve()),
        "fisa_rows_inserted": len(fisa_ids),
        "fisa_ids": fisa_ids,
        "plan_rows_inserted": len(plan_items),
        "fisa_preview": [
            {
                "id": fisa_id,
                "cod": fisa.cod,
                "nume": fisa.nume,
                "semestru": fisa.semestru,
                "credite": fisa.credite,
                "evaluare": fisa.evaluare,
                "ponderi": fisa.ponderi,
            }
            for fisa_id, fisa in zip(fisa_ids[:10], fise_items[:10], strict=False)
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDF -> OCR/text -> parse -> validate -> SQLite pipeline"
    )
    parser.add_argument("--fisa-pdf", required=True, help="Path to fisa PDF")
    parser.add_argument("--plan-pdf", required=True, help="Path to plan PDF")
    parser.add_argument(
        "--is-fisa-scanned", action="store_true", help="Use OCR for fisa PDF"
    )
    parser.add_argument(
        "--is-plan-scanned", action="store_true", help="Use OCR for plan PDF"
    )
    parser.add_argument(
        "--db-path",
        default="data/discipline.db",
        help="SQLite DB path (default: data/discipline.db)",
    )
    parser.add_argument(
        "--ocr-lang",
        default="ro,en",
        help="EasyOCR languages, comma-separated, default: ro,en",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fisa_pdf_path = Path(args.fisa_pdf).expanduser().resolve()
    plan_pdf_path = Path(args.plan_pdf).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()

    if not fisa_pdf_path.exists():
        print(json.dumps({"status": "error", "message": "fisa PDF not found"}))
        return 1
    if not plan_pdf_path.exists():
        print(json.dumps({"status": "error", "message": "plan PDF not found"}))
        return 1

    try:
        result = run_pipeline(
            fisa_pdf_path=fisa_pdf_path,
            plan_pdf_path=plan_pdf_path,
            is_fisa_scanned=args.is_fisa_scanned,
            is_plan_scanned=args.is_plan_scanned,
            db_path=db_path,
            ocr_lang=args.ocr_lang,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "validation_failed",
                    "errors": exc.errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except Exception as exc:  # pragma: no cover
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "processing_failed",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
