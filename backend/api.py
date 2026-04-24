from __future__ import annotations

import os
import contextlib
import ssl
import re
import tempfile
from pathlib import Path
import unicodedata
from typing import Generator
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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
    from plan_parser import _build_from_cunoscute, parse_plan_from_text_heuristic
    from validation_service import valideaza_nivel2
    PLAN_VALIDATION_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    _build_from_cunoscute = None
    parse_plan_from_text_heuristic = None
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

app = FastAPI(title="PDF Ingestion & Validation Service", version="2.0.0")
BASE_DIR = Path(__file__).resolve().parent
COMPARE_OUTPUT_DIR = BASE_DIR / "compare_output"


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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
        sursa_plan = "parser_standard"
        plan_brut = parse_plan(plan_text)

        if not plan_brut or len(plan_brut) < 5:
            sursa_plan = "parser_heuristic_ocr"
            plan_brut = parse_plan_from_text_heuristic(plan_text)

        if not plan_brut or len(plan_brut) < 5:
            sursa_plan = "fallback_cunoscute"
            plan_brut = _build_from_cunoscute()

        plan = [p for p in plan_brut if p]

        # Aggressively normalize names for robust matching to solve OCR noise.
        for fisa in fise:
            fisa.nume = _get_comparable_name(fisa.nume)
        for disciplina_plan in plan:
            disciplina_plan.nume = _get_comparable_name(disciplina_plan.nume)

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
