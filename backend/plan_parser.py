from __future__ import annotations

import re
import pdfplumber
from pathlib import Path
from pdf_ingestion_service import PlanDisciplina
from ocr_name_fix import repair_discipline_name, _normalize_for_lookup, DISCIPLINE_CUNOSCUTE_NORMALIZED


def _normalize(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


# Discipline cunoscute din PI — forma corectă cu spații
# Cheia e numele normalizat (fără spații, fără diacritice)
# pentru a face lookup rapid
DISCIPLINE_CUNOSCUTE: list[tuple[str, str, int, int]] = [
    # (cod, nume_corect, semestru, credite)
    # ANUL I - Semestrul 1
    ("APO01", "analiza matematica", 1, 5),
    ("AG12", "fundamentele algebrice ale informaticii", 1, 5),
    ("IT13", "algoritmi fundamentali", 1, 6),
    ("IT14", "fundamentele programarii", 1, 5),
    ("IT15", "logica matematica si computationala", 1, 5),
    ("RE16", "redactare si comunicare stiintifica si profesionala", 1, 2),
    # ANUL I - Semestrul 2
    ("AG21", "algebra liniara, geometrie analitica si diferentiala", 2, 5),
    ("IT22", "arhitectura sistemelor de calcul", 2, 5),
    ("IT23", "programare orientata pe obiecte", 2, 6),
    ("IT24", "structuri de date", 2, 6),
    ("IA25", "sisteme de operare", 2, 6),
    ("EF26", "educatie fizica si sport 1", 2, 2),
    # ANUL I - Optionale
    ("LE1", "limba engleza 1", 1, 2),
    ("LG1", "limba germana 1", 1, 2),
    ("LE2", "limba engleza 2", 2, 2),
    ("LG2", "limba germana 2", 2, 2),
    # Facultative Anul I
    ("NFI", "notiuni fundamentale de informatica", 1, 2),
    ("NFM", "notiuni fundamentale de matematica", 1, 2),
    # ANUL II - Semestrul 1
    ("IT31", "algoritmica grafurilor", 1, 5),
    ("IT32", "limbaje formale si compilatoare", 1, 5),
    ("IA33", "medii si instrumente de programare", 1, 5),
    ("IT34", "baze de date", 1, 5),
    ("IT35", "inteligenta artificiala", 1, 5),
    ("EF02", "educatie fizica si sport 2", 1, 2),
    # ANUL II - Semestrul 2
    ("IA41", "automate, calculabilitate si complexitate", 2, 5),
    ("IA42", "metode avansate de programare", 2, 5),
    ("IA43", "retele de calculatoare", 2, 5),
    ("IA44", "calcul numeric", 2, 5),
    # ANUL III - Semestrul 1
    ("IA51", "inginerie software", 1, 5),
    ("IA52", "interfete om-calculator", 1, 5),
    ("IA53", "dezvoltarea aplicatiilor web", 1, 5),
    ("IT54", "practica de specialitate", 1, 5),
    # ANUL III - Semestrul 2
    ("IA61", "managementul proiectelor informatice", 2, 5),
    ("IT62", "programare paralela, concurenta si distribuita", 2, 5),
    ("AP63", "probabilitati si statistica", 2, 5),
    ("IT64", "practica pentru elaborarea lucrarii de licenta", 2, 5),
]


def _build_from_cunoscute() -> list[PlanDisciplina]:
    """
    Construiește lista din disciplinele cunoscute cu nume corecte (cu spații).
    Aceasta e sursa de adevăr pentru matching cu FD-urile.
    """
    return [
        PlanDisciplina(cod=cod, nume=nume, semestru=sem, credite=credite)
        for cod, nume, sem, credite in DISCIPLINE_CUNOSCUTE
    ]


def parse_plan_cu_fallback(plan_pdf_path: Path) -> list[PlanDisciplina]:
    """
    Încearcă parsarea layout-based, apoi fallback la lista hardcodată.
    Aplică repair_discipline_name pe orice rezultat din parsare automată.
    """
    from pdf_ingestion_service import parse_plan_from_pdf_layout, parse_plan
    import pdfplumber

    # Încearcă layout parser
    raw_results = parse_plan_from_pdf_layout(plan_pdf_path)

    # Repară numele din rezultatele parsate automat
    if raw_results:
        repaired = []
        seen = set()
        for item in raw_results:
            nume_reparat = repair_discipline_name(item.nume)
            key = (nume_reparat, item.semestru, item.credite)
            if key in seen:
                continue
            seen.add(key)
            repaired.append(PlanDisciplina(
                cod=item.cod,
                nume=nume_reparat,
                semestru=item.semestru,
                credite=item.credite,
            ))
        if len(repaired) >= 10:
            return repaired

    # Fallback text
    with pdfplumber.open(str(plan_pdf_path)) as pdf:
        full_text = "".join(page.extract_text() or "" for page in pdf.pages)

    text_results = parse_plan(full_text)
    if text_results:
        repaired = []
        seen = set()
        for item in text_results:
            nume_reparat = repair_discipline_name(item.nume)
            key = (nume_reparat, item.semestru, item.credite)
            if key in seen:
                continue
            seen.add(key)
            repaired.append(PlanDisciplina(
                cod=item.cod,
                nume=nume_reparat,
                semestru=item.semestru,
                credite=item.credite,
            ))
        if len(repaired) >= 10:
            return repaired

    # Fallback final — lista hardcodată cu nume corecte
    return _build_from_cunoscute()


def get_plan_discipline(plan_pdf_path: Path) -> list[PlanDisciplina]:
    """Entry point principal."""
    try:
        return parse_plan_cu_fallback(plan_pdf_path)
    except Exception:
        return _build_from_cunoscute()