from __future__ import annotations

import os
import contextlib
import ssl
import re
import json
import sqlite3
import base64
import hashlib
import hmac
import tempfile
from pathlib import Path
import unicodedata
from typing import Generator
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from docx import Document
    WORD_EXPORT_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    Document = None
    WORD_EXPORT_IMPORT_ERROR = exc

try:
    from pdf_visual_compare import (
        build_diff_payload,
        build_html_diff,
        build_line_view,
        extract_pdf,
    )
    PDF_COMPARE_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    build_diff_payload = None
    build_html_diff = None
    build_line_view = None
    extract_pdf = None
    PDF_COMPARE_IMPORT_ERROR = exc

try:
    from plan_parser import get_plan_discipline
    from validation_service import (
        list_discipline_competente,
        recomanda_competente,
        valideaza_nivel2,
    )
    PLAN_VALIDATION_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    get_plan_discipline = None
    list_discipline_competente = None
    recomanda_competente = None
    valideaza_nivel2 = None
    PLAN_VALIDATION_IMPORT_ERROR = exc

try:
    from pdf_ingestion_service import (
        ValidationError,
        extract_text,
        parse_fise,
        parse_plan,
        run_pipeline,
    )
    PDF_INGESTION_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    ValidationError = Exception
    extract_text = None
    parse_fise = None
    parse_plan = None
    run_pipeline = None
    PDF_INGESTION_IMPORT_ERROR = exc

try:
    from json_batch_update import batch_update_json_files
except ImportError:
    batch_update_json_files = None

try:
    from check_weights_hours import check_db as check_weights_hours_db
except ImportError:
    check_weights_hours_db = None

try:
    from validator_fd import load_fd_from_input, run_validation
    FD_VALIDATOR_IMPORT_ERROR = None
except ModuleNotFoundError:
    try:
        from backend.validator_fd import load_fd_from_input, run_validation
        FD_VALIDATOR_IMPORT_ERROR = None
    except ModuleNotFoundError as exc:
        load_fd_from_input = None
        run_validation = None
        FD_VALIDATOR_IMPORT_ERROR = exc

try:
    from fd_single_prefill_from_pi import (
        build_single_fd_html,
        choose_best_plan_match,
        extract_text_native as extract_fd_single_prefill_text,
        is_auto_code,
        load_plan_rows as load_prefill_plan_rows,
        parse_fd_probe,
    )
    FD_SINGLE_PREFILL_IMPORT_ERROR = None
except ModuleNotFoundError:
    try:
        from backend.fd_single_prefill_from_pi import (
            build_single_fd_html,
            choose_best_plan_match,
            extract_text_native as extract_fd_single_prefill_text,
            is_auto_code,
            load_plan_rows as load_prefill_plan_rows,
            parse_fd_probe,
        )
        FD_SINGLE_PREFILL_IMPORT_ERROR = None
    except ModuleNotFoundError as exc:
        build_single_fd_html = None
        choose_best_plan_match = None
        extract_fd_single_prefill_text = None
        is_auto_code = None
        load_prefill_plan_rows = None
        parse_fd_probe = None
        FD_SINGLE_PREFILL_IMPORT_ERROR = exc

try:
    from fd_migration_service import migrate_fd_pdf_to_template
    FD_MIGRATION_IMPORT_ERROR = None
except ModuleNotFoundError:
    try:
        from backend.fd_migration_service import migrate_fd_pdf_to_template
        FD_MIGRATION_IMPORT_ERROR = None
    except ModuleNotFoundError as exc:
        migrate_fd_pdf_to_template = None
        FD_MIGRATION_IMPORT_ERROR = exc

app = FastAPI(title="PDF Ingestion & Validation Service", version="2.0.0")
BASE_DIR = Path(__file__).resolve().parent
COMPARE_OUTPUT_DIR = BASE_DIR / "compare_output"
USERS_DB_PATH = BASE_DIR / "data" / "users.db"
FD_MIGRATION_TEMPLATE_PATH = BASE_DIR / "templates" / "fd_template_v2028.json"
FD_MIGRATION_MAPPING_PATH = BASE_DIR / "templates" / "fd_mapping_canonical_to_v2028.json"

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,50}$")
PASSWORD_MIN_LENGTH = 6
PASSWORD_HASH_ITERATIONS = 210_000


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


# Adăugăm middleware-ul pentru CORS
app.add_middleware(
    CORSMiddleware,
    # Permitem cereri de la serverul de dezvoltare React (Vite rulează de obicei pe 5173)
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    # Permitem toate metodele (GET, POST, etc.)
    allow_methods=["*"],
    # Permitem toate headerele
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Workaround for SSL issues with EasyOCR model download
# ---------------------------------------------------------------------------
# WARNING: This is a workaround for SSL certificate verification issues (e.g.,
# CERTIFICATE_VERIFY_FAILED) that can occur when EasyOCR tries to download
# language models. It disables SSL verification globally, which is a security
# risk. This should only be used for local development if you are behind a
# proxy or have SSL issues, and it should NOT be used in production.
# A better long-term solution is to configure your system's SSL certificates correctly.
if hasattr(ssl, "_create_unverified_context"):
    ssl._create_default_https_context = ssl._create_unverified_context



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def save_upload_to_temp_path(upload: UploadFile) -> Generator[Path, None, None]:
    """
    Saves an UploadFile to a temporary path and ensures it's cleaned up.
    This is a context manager that yields the path to the temporary file.
    """
    temp_path = None
    try:
        suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(upload.file.read())
            temp_path = Path(handle.name).resolve()
        yield temp_path
    finally:
        if temp_path and temp_path.exists():
            with contextlib.suppress(PermissionError, FileNotFoundError):
                os.unlink(temp_path)


def _get_comparable_name(text: str) -> str:
    """
    Aggressively normalizes a string for robust comparison by removing diacritics,
    non-alphanumeric characters, and all whitespace.
    e.g., "Algoritmi fundamentali 1" -> "algoritmifundamentali1"
    e.g., "a l g o r i t m i" -> "algoritmi"
    """
    if not isinstance(text, str):
        return ""
    # 1. Remove diacritics
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # 2. Lowercase and remove all non-alphanumeric characters
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _ensure_ingestion_dependencies() -> None:
    missing_dependency_error = PDF_INGESTION_IMPORT_ERROR or PLAN_VALIDATION_IMPORT_ERROR
    if missing_dependency_error is None:
        return

    raise HTTPException(
        status_code=500,
        detail={
            "status": "error",
            "message": "missing_backend_dependency",
            "error": str(missing_dependency_error),
            "hint": "Install backend requirements to use ingest/validate endpoints.",
        },
    )


def _ensure_plan_validation_dependencies() -> None:
    if PLAN_VALIDATION_IMPORT_ERROR is None:
        return

    raise HTTPException(
        status_code=500,
        detail={
            "status": "error",
            "message": "missing_backend_dependency",
            "error": str(PLAN_VALIDATION_IMPORT_ERROR),
            "hint": "Install backend requirements to use validation competency endpoints.",
        },
    )


def _ensure_visual_compare_dependencies() -> None:
    if PDF_COMPARE_IMPORT_ERROR is None:
        return

    raise HTTPException(
        status_code=500,
        detail={
            "status": "error",
            "message": "missing_backend_dependency",
            "error": str(PDF_COMPARE_IMPORT_ERROR),
            "hint": "Install backend requirements to use visual compare endpoint.",
        },
    )


def _ensure_fd_validator_dependencies() -> None:
    if FD_VALIDATOR_IMPORT_ERROR is None:
        return

    raise HTTPException(
        status_code=500,
        detail={
            "status": "error",
            "message": "missing_backend_dependency",
            "error": str(FD_VALIDATOR_IMPORT_ERROR),
            "hint": "Install backend requirements to use single FD validator endpoint.",
        },
    )


def _ensure_fd_single_prefill_dependencies() -> None:
    missing_dependency_error = FD_SINGLE_PREFILL_IMPORT_ERROR or WORD_EXPORT_IMPORT_ERROR
    if missing_dependency_error is None:
        return

    raise HTTPException(
        status_code=500,
        detail={
            "status": "error",
            "message": "missing_backend_dependency",
            "error": str(missing_dependency_error),
            "hint": "Install backend requirements to use single FD prefill + Word export endpoint.",
        },
    )


def _ensure_fd_migration_dependencies() -> None:
    missing_dependency_error = FD_MIGRATION_IMPORT_ERROR or WORD_EXPORT_IMPORT_ERROR
    if missing_dependency_error is None:
        return

    raise HTTPException(
        status_code=500,
        detail={
            "status": "error",
            "message": "missing_backend_dependency",
            "error": str(missing_dependency_error),
            "hint": "Install backend requirements to use FD template migration endpoint.",
        },
    )


def _resolve_existing_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.exists():
        return candidate.resolve()

    backend_candidate = (BASE_DIR / raw_path).resolve()
    if backend_candidate.exists():
        return backend_candidate

    fallback_data = (BASE_DIR / "data" / Path(raw_path).name).resolve()
    if fallback_data.exists():
        return fallback_data

    raise FileNotFoundError(f"Path not found: {raw_path}")


def _normalize_username(value: str) -> str:
    return (value or "").strip()


def _normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _ensure_auth_database() -> None:
    USERS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(USERS_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    password_bytes = (password or "").encode("utf-8")
    salt_bytes = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password_bytes,
        salt_bytes,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt_bytes).decode("ascii")
    hash_b64 = base64.b64encode(digest).decode("ascii")
    return salt_b64, hash_b64


def _verify_password(password: str, salt_b64: str, hash_b64: str) -> bool:
    try:
        salt_bytes = base64.b64decode(salt_b64.encode("ascii"))
        expected_hash = base64.b64decode(hash_b64.encode("ascii"))
    except Exception:
        return False

    _, computed_hash_b64 = _hash_password(password, salt=salt_bytes)
    try:
        computed_hash = base64.b64decode(computed_hash_b64.encode("ascii"))
    except Exception:
        return False
    return hmac.compare_digest(expected_hash, computed_hash)


def _validate_register_input(username: str, email: str, password: str) -> None:
    if not username or not email or not password:
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "All fields are required"},
        )

    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "message": "Username must be 3-50 chars and contain only letters, numbers, ., _, -",
            },
        )

    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "Please enter a valid email address"},
        )

    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "message": f"Password must have at least {PASSWORD_MIN_LENGTH} characters",
            },
        )


def _validate_login_input(username: str, password: str) -> None:
    if not username or not password:
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "Username and password are required"},
        )


def _get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, username, email, password_salt, password_hash
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()


def _get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, username, email, password_salt, password_hash
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()


def _string_value(value: str | int | None) -> str:
    if value is None:
        return ""
    return str(value)


def _append_docx_section(document, title: str, rows: list[tuple[str, str | int | None]]) -> None:
    heading = document.add_paragraph()
    heading_run = heading.add_run(title)
    heading_run.bold = True

    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Camp"
    table.rows[0].cells[1].text = "Valoare"

    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = _string_value(label)
        cells[1].text = _string_value(value)


def _build_single_fd_docx(plan_row, debug_source: str, output_docx_path: Path) -> None:
    document = Document()
    cod_value = plan_row.cod if not is_auto_code(plan_row.cod) else ""

    document.add_heading("Fisa Disciplinei", level=1)
    document.add_paragraph(f"Denumirea disciplinei: {_string_value(plan_row.nume) or '-'}")
    document.add_paragraph(f"Sursa precompletare: {debug_source}")

    _append_docx_section(
        document,
        "1. Date despre program",
        [
            ("1.1 Institutia de invatamant superior", ""),
            ("1.2 Facultatea", ""),
            ("1.3 Departamentul", ""),
            ("1.4 Domeniul de studii de licenta", ""),
            ("1.5 Ciclul de studii", ""),
            ("1.6 Programul de studii / Calificarea", ""),
        ],
    )
    _append_docx_section(
        document,
        "2. Date despre disciplina",
        [
            ("2.0 Cod disciplina", cod_value),
            ("2.1 Denumirea disciplinei", plan_row.nume),
            ("2.2 Titularul activitatilor de curs", ""),
            ("2.3 Titularul activitatilor de seminar/laborator/proiect", ""),
            ("2.4 Anul de studiu", ""),
            ("2.5 Semestrul", plan_row.semestru),
            ("2.6 Tipul de evaluare", ""),
            ("2.7 Regimul disciplinei", ""),
        ],
    )
    _append_docx_section(
        document,
        "3. Timpul total estimat (ore pe semestru)",
        [
            ("3.1 Numar de ore pe saptamana", ""),
            ("3.4 Total ore din planul de invatamant", ""),
            ("3.8 Total ore pe semestru", ""),
            ("3.9 Numarul de credite", plan_row.credite),
        ],
    )
    _append_docx_section(document, "4. Preconditii", [("Detalii", "")])
    _append_docx_section(document, "5. Conditii", [("Detalii", "")])
    _append_docx_section(document, "6. Competente specifice acumulate", [("Detalii", "")])
    _append_docx_section(document, "7. Obiectivele disciplinei", [("Detalii", "")])
    _append_docx_section(document, "8.1 Curs", [("Detalii", "")])
    _append_docx_section(document, "8.2 Seminar / laborator / proiect", [("Detalii", "")])
    _append_docx_section(document, "9. Coroborarea continuturilor disciplinei", [("Detalii", "")])
    _append_docx_section(
        document,
        "10. Evaluare",
        [
            ("Tip activitate", "Standarde minime de performanta"),
            ("Curs", ""),
            ("Seminar/Laborator", ""),
            ("Proiect", ""),
        ],
    )

    output_docx_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_docx_path)


def _flatten_template_for_docx(value, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_template_for_docx(nested_value, nested_prefix))
        return rows

    if isinstance(value, list):
        rows.append((prefix, json.dumps(value, ensure_ascii=False)))
        return rows

    if value is None:
        rows.append((prefix, ""))
        return rows

    rows.append((prefix, str(value)))
    return rows


def _build_migrated_template_docx(
    migrated_template: dict,
    report_payload: dict,
    output_docx_path: Path,
) -> None:
    document = Document()
    disciplina_payload = migrated_template.get("disciplina", {})
    disciplina_name = "-"
    if isinstance(disciplina_payload, dict):
        disciplina_name = str(disciplina_payload.get("denumire") or "-")

    document.add_heading("Fisa Disciplinei - Template Migrat", level=1)
    document.add_paragraph(f"Disciplina: {disciplina_name}")
    document.add_paragraph(
        f"Acoperire campuri obligatorii: {round(float(report_payload.get('coverage_required', 0.0)) * 100, 2)}%"
    )

    missing_required = report_payload.get("required_fields_missing", [])
    if isinstance(missing_required, list) and missing_required:
        document.add_paragraph(
            "Campuri obligatorii lipsa: " + ", ".join(str(item) for item in missing_required)
        )
    else:
        document.add_paragraph("Campuri obligatorii lipsa: -")

    top_level_sections = [
        ("Date Program", migrated_template.get("program", {})),
        ("Date Disciplina", migrated_template.get("disciplina", {})),
        ("Timp Total", migrated_template.get("timp", {})),
        ("Preconditii", migrated_template.get("preconditii", {})),
        ("Conditii", migrated_template.get("conditii", {})),
        ("Competente", migrated_template.get("competente", {})),
        ("Obiective", migrated_template.get("obiective", {})),
        ("Continut", migrated_template.get("continut", {})),
        ("Evaluare", migrated_template.get("evaluare", {})),
    ]

    for section_title, section_payload in top_level_sections:
        rows = _flatten_template_for_docx(section_payload)
        _append_docx_section(document, section_title, rows if rows else [("valoare", "")])

    output_docx_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_docx_path)


def _migrate_fd_template_blocking(fisa_tmp: Path) -> dict:
    if not FD_MIGRATION_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template JSON not found: {FD_MIGRATION_TEMPLATE_PATH}")
    if not FD_MIGRATION_MAPPING_PATH.exists():
        raise FileNotFoundError(f"Mapping JSON not found: {FD_MIGRATION_MAPPING_PATH}")

    canonical_model, migrated_template, full_report = migrate_fd_pdf_to_template(
        input_pdf=fisa_tmp,
        template_json_path=FD_MIGRATION_TEMPLATE_PATH,
        mapping_json_path=FD_MIGRATION_MAPPING_PATH,
        scanned=False,
        ocr_lang="ro,en",
    )

    COMPARE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_token = uuid4().hex
    canonical_name = f"fd_migration_{file_token}_canonical.json"
    template_name = f"fd_migration_{file_token}_template.json"
    report_name = f"fd_migration_{file_token}_report.json"
    docx_name = f"fd_migration_{file_token}.docx"

    canonical_path = COMPARE_OUTPUT_DIR / canonical_name
    template_path = COMPARE_OUTPUT_DIR / template_name
    report_path = COMPARE_OUTPUT_DIR / report_name
    docx_path = COMPARE_OUTPUT_DIR / docx_name

    canonical_path.write_text(json.dumps(canonical_model, ensure_ascii=False, indent=2), encoding="utf-8")
    template_path.write_text(json.dumps(migrated_template, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8")
    _build_migrated_template_docx(
        migrated_template=migrated_template,
        report_payload=full_report,
        output_docx_path=docx_path,
    )

    disciplina_payload = canonical_model.get("disciplina", {})
    disciplina_name = "-"
    if isinstance(disciplina_payload, dict):
        disciplina_name = str(
            migrated_template.get("disciplina", {}).get("denumire")
            or disciplina_payload.get("nume")
            or "-"
        )

    return {
        "status": "success",
        "message": "fd_template_migrated",
        "disciplina": disciplina_name,
        "coverage_required": float(full_report.get("coverage_required", 0.0)),
        "required_fields_missing": full_report.get("required_fields_missing", []),
        "template_preview": migrated_template,
        "output_template_url": f"/migrate/fd-template-file/{template_name}",
        "output_canonical_url": f"/migrate/fd-template-file/{canonical_name}",
        "output_report_url": f"/migrate/fd-template-file/{report_name}",
        "output_docx_url": f"/migrate/fd-template-file/{docx_name}",
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/register")
def register_user(payload: RegisterRequest) -> dict:
    _ensure_auth_database()
    username = _normalize_username(payload.username)
    email = _normalize_email(payload.email)
    password = payload.password or ""
    _validate_register_input(username, email, password)

    password_salt, password_hash = _hash_password(password)

    try:
        with sqlite3.connect(USERS_DB_PATH) as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_salt, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (username, email, password_salt, password_hash),
            )
            conn.commit()
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        with sqlite3.connect(USERS_DB_PATH) as conn:
            if _get_user_by_username(conn, username):
                raise HTTPException(
                    status_code=409,
                    detail={"status": "error", "message": "Username already exists. Please choose another."},
                )
            if _get_user_by_email(conn, email):
                raise HTTPException(
                    status_code=409,
                    detail={"status": "error", "message": "Email already registered. Please use another email."},
                )
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": "Failed to register user"},
        )

    return {
        "status": "success",
        "message": "Registration successful! You can now log in.",
        "user": {
            "id": user_id,
            "username": username,
            "email": email,
        },
    }


@app.post("/auth/login")
def login_user(payload: LoginRequest) -> dict:
    _ensure_auth_database()
    username = _normalize_username(payload.username)
    password = payload.password or ""
    _validate_login_input(username, password)

    with sqlite3.connect(USERS_DB_PATH) as conn:
        user = _get_user_by_username(conn, username)

    invalid_credentials_error = HTTPException(
        status_code=401,
        detail={"status": "error", "message": "Invalid username or password"},
    )

    if not user:
        raise invalid_credentials_error

    if not _verify_password(password, str(user["password_salt"]), str(user["password_hash"])):
        raise invalid_credentials_error

    return {
        "status": "success",
        "message": "Login successful!",
        "user": {
            "id": int(user["id"]),
            "username": str(user["username"]),
            "email": str(user["email"]),
        },
    }


@app.get("/competencies/subjects")
def get_competency_subjects() -> dict:
    _ensure_plan_validation_dependencies()
    return {
        "status": "success",
        "subjects": list_discipline_competente(),
    }


@app.get("/competencies/recommend")
def get_competencies_for_subject(subject: str) -> dict:
    _ensure_plan_validation_dependencies()
    subject_clean = (subject or "").strip()
    if not subject_clean:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "subject is required"},
        )

    competencies = recomanda_competente(subject_clean)
    return {
        "status": "success",
        "subject": subject_clean,
        "count": len(competencies),
        "competencies": competencies,
    }


def _compare_visual_pdfs_blocking(left_pdf_path: Path, right_pdf_path: Path) -> dict:
    left_data = extract_pdf(left_pdf_path)
    right_data = extract_pdf(right_pdf_path)

    left_lines = build_line_view(left_data)
    right_lines = build_line_view(right_data)
    diff_payload = build_diff_payload(left_lines, right_lines)

    COMPARE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_name = f"comparison_{uuid4().hex}.html"
    report_path = COMPARE_OUTPUT_DIR / report_name
    report_html = build_html_diff(
        left_lines=left_lines,
        right_lines=right_lines,
        left_label=Path(left_data.source_file).name,
        right_label=Path(right_data.source_file).name,
        summary=diff_payload["summary"],
    )
    report_path.write_text(report_html, encoding="utf-8")

    return {
        "status": "success",
        "left_source_pdf": left_data.source_file,
        "right_source_pdf": right_data.source_file,
        "left_label": Path(left_data.source_file).name,
        "right_label": Path(right_data.source_file).name,
        "summary": diff_payload["summary"],
        "changes": diff_payload["changes"],
        "html_report_url": f"/compare/visual-report/{report_name}",
    }


@app.post("/compare/visual-pdf")
async def compare_visual_pdf(
    left_pdf: UploadFile = File(..., description="Primul PDF (stanga)"),
    right_pdf: UploadFile = File(..., description="Al doilea PDF (dreapta)"),
) -> dict:
    _ensure_visual_compare_dependencies()

    with save_upload_to_temp_path(left_pdf) as left_tmp, \
         save_upload_to_temp_path(right_pdf) as right_tmp:
        try:
            return await run_in_threadpool(
                _compare_visual_pdfs_blocking,
                left_pdf_path=left_tmp,
                right_pdf_path=right_tmp,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "compare_visual_pdf_failed",
                    "error": str(exc),
                },
            ) from exc


@app.get("/compare/visual-report/{report_name}")
def get_visual_report(report_name: str):
    safe_name = Path(report_name).name
    if safe_name != report_name or not safe_name.endswith(".html"):
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "invalid_report_name"},
        )

    report_path = COMPARE_OUTPUT_DIR / safe_name
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "report_not_found"},
        )

    return FileResponse(report_path, media_type="text/html")


@app.post("/ingest")
async def ingest(
    fisa_pdf: UploadFile = File(...),
    plan_pdf: UploadFile = File(...),
    is_fisa_scanned: bool = Form(False),
    is_plan_scanned: bool = Form(False),
    db_path: str = Form("data/discipline.db"),
    ocr_lang: str = Form("ro,en"),
) -> dict:
    _ensure_ingestion_dependencies()

    with save_upload_to_temp_path(fisa_pdf) as fisa_tmp, \
         save_upload_to_temp_path(plan_pdf) as plan_tmp:
        try:
            # Rulăm pipeline-ul (care conține operațiuni blocante precum OCR)
            # într-un thread separat pentru a nu bloca serverul.
            result = await run_in_threadpool(
                run_pipeline,
                fisa_pdf_path=fisa_tmp,
                plan_pdf_path=plan_tmp,
                is_fisa_scanned=is_fisa_scanned,
                is_plan_scanned=is_plan_scanned,
                db_path=Path(db_path).expanduser().resolve(),
                ocr_lang=ocr_lang,
            )
            return result
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "error",
                    "message": "validation_failed",
                    "errors": exc.errors,
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "processing_failed",
                    "error": str(exc),
                },
            ) from exc


def _validate_blocking_logic(fisa_tmp, plan_tmp, is_fisa_scanned, is_plan_scanned, ocr_lang):
    """Helper function to run blocking validation logic."""
    _ensure_ingestion_dependencies()

    try:
        # 1. Extragere text FD
        fisa_text = extract_text(
            fisa_tmp, scanned=is_fisa_scanned, ocr_lang=ocr_lang
        )

        # 2. Parsare FD
        # Filtrăm rezultatele pentru a elimina eventualele intrări goale (None)
        fise_brute = parse_fise(fisa_text)
        fise = [f for f in fise_brute if f]

        # 3. Parsare PI
        plan_text = extract_text(
            plan_tmp, scanned=is_plan_scanned, ocr_lang=ocr_lang
        )

        # Încercăm mai multe strategii de parsare pentru PI, de la cea mai
        # specifică la cea mai generală (fallback).
        sursa_plan = "fallback_cunoscute"
        plan_brut = get_plan_discipline(plan_tmp)

        plan = [p for p in plan_brut if p]

        # Aggressively normalize names for robust matching to solve OCR noise.
        

        if not fise:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "error",
                    "message": "Nu s-a putut extrage nicio Fișă de Disciplină din PDF-ul uploadat.",
                },
            )

        if not plan:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "error",
                    "message": "Nu s-a putut extrage nicio disciplină din Planul de Învățământ.",
                },
            )

        # 4. Validare Nivel 2
        raport = valideaza_nivel2(fise=fise, plan=plan)

        return {
            "status": "success",
            "plan_extras": len(plan),
            "sursa_plan": sursa_plan,
            **raport.to_dict(),
        }

    except Exception as exc:
        # Propagate exceptions to be handled by the main endpoint
        raise exc


@app.post("/validate")
async def validate(
    fisa_pdf: UploadFile = File(..., description="PDF cu Fișa/Fișele de Disciplină"),
    plan_pdf: UploadFile = File(..., description="PDF cu Planul de Învățământ"),
    is_fisa_scanned: bool = Form(False, description="Bifați dacă FD-ul e scanat (OCR)"),
    is_plan_scanned: bool = Form(False, description="Bifați dacă PI-ul e scanat (OCR)"),
    ocr_lang: str = Form("ro,en", description="Limbi OCR, separate prin virgulă"),
) -> dict:
    """
    Nivel 2 — Validare cross-document FD ↔ PI.

    Verifică pentru fiecare Fișă de Disciplină:
    - Există disciplina în Planul de Învățământ?
    - Creditele coincid?
    - Semestrul coincide?
    - Disciplinele din PI fără FD corespunzătoare.

    Returnează un raport structurat cu severitate: eroare / avertisment / ok.
    """
    _ensure_ingestion_dependencies()

    with save_upload_to_temp_path(fisa_pdf) as fisa_tmp, \
         save_upload_to_temp_path(plan_pdf) as plan_tmp:
        try:
            # Rulăm logica de validare (care conține operațiuni blocante precum OCR)
            # într-un thread separat pentru a nu bloca serverul.
            result = await run_in_threadpool(
                _validate_blocking_logic,
                fisa_tmp=fisa_tmp,
                plan_tmp=plan_tmp,
                is_fisa_scanned=is_fisa_scanned,
                is_plan_scanned=is_plan_scanned,
                ocr_lang=ocr_lang,
            )
            return result
        except HTTPException:
            # Re-throw HTTPExceptions raised from the background thread
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "Eroare la procesarea PDF-urilor.",
                    "error": str(exc),
                },
            ) from exc


def _validate_single_fd_blocking(fisa_tmp: Path) -> dict:
    canonical = load_fd_from_input(
        input_path=fisa_tmp,
        scanned=False,
        ocr_lang="ro,en",
    )
    result = run_validation(canonical)
    return {
        "status": "success",
        **result,
    }


@app.post("/validate/fd-single")
async def validate_fd_single(
    fisa_pdf: UploadFile = File(..., description="PDF cu o singura Fisa de Disciplina"),
) -> dict:
    _ensure_fd_validator_dependencies()

    with save_upload_to_temp_path(fisa_pdf) as fisa_tmp:
        try:
            result = await run_in_threadpool(
                _validate_single_fd_blocking,
                fisa_tmp=fisa_tmp,
            )
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "single_fd_validation_failed",
                    "error": str(exc),
                },
            ) from exc


def _prefill_single_fd_template_blocking(fisa_tmp: Path, db_path: str) -> dict:
    resolved_db_path = _resolve_existing_path(db_path)
    raw_text = extract_fd_single_prefill_text(fisa_tmp)
    probe = parse_fd_probe(raw_text)

    with sqlite3.connect(resolved_db_path) as conn:
        plan_rows = load_prefill_plan_rows(conn)

    matched, strategy, score = choose_best_plan_match(probe, plan_rows)
    if not matched:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "message": "Nu am putut identifica disciplina in planul de invatamant.",
            },
        )

    COMPARE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_name = f"fd_single_prefill_{uuid4().hex}.html"
    report_path = COMPARE_OUTPUT_DIR / report_name
    docx_name = f"fd_single_prefill_{uuid4().hex}.docx"
    docx_path = COMPARE_OUTPUT_DIR / docx_name
    debug_name = f"fd_single_prefill_{uuid4().hex}.json"
    debug_path = COMPARE_OUTPUT_DIR / debug_name

    html_content = build_single_fd_html(matched, debug_source=f"PI/{strategy}")
    report_path.write_text(html_content, encoding="utf-8")
    _build_single_fd_docx(matched, debug_source=f"PI/{strategy}", output_docx_path=docx_path)

    debug_payload = {
        "status": "success",
        "message": "single_fd_prefilled_from_pi",
        "db_path": str(resolved_db_path),
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
        "output_html_url": f"/prefill/fd-single-report/{report_name}",
        "output_docx_url": f"/prefill/fd-single-docx/{docx_name}",
        "output_html_path": str(report_path),
        "output_docx_path": str(docx_path),
        "output_json_path": str(debug_path),
    }
    debug_path.write_text(json.dumps(debug_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "success",
        "message": "single_fd_prefilled_from_pi",
        "matched_discipline": matched.nume,
        "output_html_url": f"/prefill/fd-single-report/{report_name}",
        "output_docx_url": f"/prefill/fd-single-docx/{docx_name}",
    }


@app.post("/prefill/fd-single-template")
async def prefill_fd_single_template(
    fisa_pdf: UploadFile = File(..., description="PDF cu o singura Fisa de Disciplina"),
) -> dict:
    _ensure_fd_single_prefill_dependencies()

    with save_upload_to_temp_path(fisa_pdf) as fisa_tmp:
        try:
            result = await run_in_threadpool(
                _prefill_single_fd_template_blocking,
                fisa_tmp=fisa_tmp,
                db_path="data/discipline.db",
            )
            return result
        except HTTPException:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "message": "database_not_found",
                    "error": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "single_fd_prefill_failed",
                    "error": str(exc),
                },
            ) from exc


@app.get("/prefill/fd-single-report/{report_name}")
def get_fd_single_prefill_report(report_name: str):
    safe_name = Path(report_name).name
    if (
        safe_name != report_name
        or not safe_name.endswith(".html")
        or not safe_name.startswith("fd_single_prefill_")
    ):
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "invalid_report_name"},
        )

    report_path = COMPARE_OUTPUT_DIR / safe_name
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "report_not_found"},
        )

    return FileResponse(report_path, media_type="text/html")


@app.get("/prefill/fd-single-docx/{docx_name}")
def get_fd_single_prefill_docx(docx_name: str):
    safe_name = Path(docx_name).name
    if (
        safe_name != docx_name
        or not safe_name.endswith(".docx")
        or not safe_name.startswith("fd_single_prefill_")
    ):
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "invalid_docx_name"},
        )

    docx_path = COMPARE_OUTPUT_DIR / safe_name
    if not docx_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "docx_not_found"},
        )

    return FileResponse(
        docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )


@app.post("/migrate/fd-template")
async def migrate_fd_template(
    fisa_pdf: UploadFile = File(..., description="PDF cu o singura Fisa de Disciplina"),
) -> dict:
    _ensure_fd_migration_dependencies()

    with save_upload_to_temp_path(fisa_pdf) as fisa_tmp:
        try:
            result = await run_in_threadpool(
                _migrate_fd_template_blocking,
                fisa_tmp=fisa_tmp,
            )
            return result
        except HTTPException:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "message": "template_assets_not_found",
                    "error": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "fd_template_migration_failed",
                    "error": str(exc),
                },
            ) from exc


@app.get("/migrate/fd-template-file/{file_name}")
def get_migrated_fd_template_file(file_name: str):
    safe_name = Path(file_name).name
    if safe_name != file_name or not safe_name.startswith("fd_migration_"):
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "invalid_file_name"},
        )

    if not (safe_name.endswith(".json") or safe_name.endswith(".docx")):
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "invalid_file_extension"},
        )

    file_path = COMPARE_OUTPUT_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "file_not_found"},
        )

    if safe_name.endswith(".docx"):
        return FileResponse(
            file_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=safe_name,
        )

    return FileResponse(file_path, media_type="application/json", filename=safe_name)


@app.post("/batch-update")
async def batch_update(
    old_text: str = Form(..., description="Textul de căutat"),
    new_text: str = Form(..., description="Textul nou"),
    json_dir: str = Form("pdf"),
    target_json_file: str | None = Form(None, description="Nume fișier JSON țintă (opțional)"),
) -> dict:
    if batch_update_json_files is None:
        raise HTTPException(status_code=501, detail="JSON batch update service not available")
    
    try:
        search_dir = Path(json_dir)
        if not search_dir.exists():
            search_dir = BASE_DIR / json_dir
            
        if not search_dir.exists():
             raise FileNotFoundError(f"Folderul cu JSON-uri nu a fost găsit: {json_dir}")

        results = batch_update_json_files(
            directory=search_dir,
            old_text=old_text,
            new_text=new_text,
            target_file=target_json_file,
        )
        return {
            "status": "success",
            "results": results,
            "directory_used": str(search_dir)
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "Eroare la actualizarea fișierelor JSON.",
                "error": str(exc),
            },
        )

@app.get("/checks/weights-hours")
async def check_weights_and_hours(
    db_path: str = "data/discipline_new.db",
) -> dict:
    if check_weights_hours_db is None:
        raise HTTPException(
            status_code=501,
            detail="check_weights_hours service not available",
        )

    try:
        resolved_db_path = _resolve_existing_path(db_path)
        results = check_weights_hours_db(resolved_db_path)
        if results.get("status") == "error":
            raise FileNotFoundError(results.get("error", "Unknown database error"))
        return results
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "message": "database_not_found",
                "error": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "weights_hours_check_failed",
                "error": str(exc),
            },
        ) from exc
