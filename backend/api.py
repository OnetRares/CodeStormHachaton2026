from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .pdf_ingestion_service import ValidationError, run_pipeline


app = FastAPI(title="PDF Ingestion Service", version="1.0.0")


def save_upload_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(upload.file.read())
        return Path(handle.name).resolve()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(
    fisa_pdf: UploadFile = File(...),
    plan_pdf: UploadFile = File(...),
    is_fisa_scanned: bool = Form(False),
    is_plan_scanned: bool = Form(False),
    db_path: str = Form("data/discipline.db"),
    ocr_lang: str = Form("ro,en"),
) -> dict:
    fisa_tmp = save_upload_temp(fisa_pdf)
    plan_tmp = save_upload_temp(plan_pdf)
    try:
        result = run_pipeline(
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
    finally:
        for tmp_path in (fisa_tmp, plan_tmp):
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
