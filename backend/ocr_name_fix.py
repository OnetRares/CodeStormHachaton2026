"""
Modul auxiliar: repară numele disciplinelor extrase din PDF-uri parțial scanate.

Cum se folosește:
  - Importezi `repair_discipline_name` și o aplici pe `fisa.nume` după parsare
  - SAU înlocuiești `compact_spelled_words` din pdf_ingestion_service.py
    cu versiunea îmbunătățită de mai jos

Problema: unele FD-uri sunt scanate, OCR-ul desparte literele cu spații:
  "a l go r i tm i f unda m en t al i"  →  "algoritmi fundamentali"
  "noti un i f unda m e nta le de i n fo r mat ica" → "notiuni fundamentale de informatica"
"""
from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Dicționar de nume cunoscute — normalizate fără diacritice
# Folosit ca fallback când reconstrucția automată eșuează
# ---------------------------------------------------------------------------
DISCIPLINE_CUNOSCUTE_NORMALIZED: dict[str, str] = {
    # Varianta distorsionată (OCR) → varianta corectă
    "a l go r i tm i f unda m en t al i": "algoritmi fundamentali",
    "algoritmifundamentali": "algoritmi fundamentali",
    "noti un i f unda m e nta le de i n fo r mat ica": "notiuni fundamentale de informatica",
    "notiunifundamentaledeinformatica": "notiuni fundamentale de informatica",
    "noti un i f unda m ent al edem at ema t i ca": "notiuni fundamentale de matematica",
    "notiunifundamentaledematematica": "notiuni fundamentale de matematica",
    "analizamatematica": "analiza matematica",
    "fundamentelealgebricealeinformaticii": "fundamentele algebrice ale informaticii",
    "fundamenteleprogramarii": "fundamentele programarii",
    "logicamatematicasicomputationala": "logica matematica si computationala",
    "eticasiintegritateacademicai": "etica si integritate academica i",
    "educatiefizicasisport12": "educatie fizica si sport 1",
    "educatiefizicasisport1": "educatie fizica si sport 1",
    "educatiefizicasisport2": "educatie fizica si sport 2",
    "limbaengleza1": "limba engleza 1",
    "limbaengleza2": "limba engleza 2",
    "limbagermana1": "limba germana 1",
    "limbagermana2": "limba germana 2",
    "limbagermana12": "limba germana 1",
    "algebraliniarageometrieanaliticasidiferentiala": "algebra liniara, geometrie analitica si diferentiala",
    "arhitecturasistemelordecalcul": "arhitectura sistemelor de calcul",
    "programareorientatapeobiecte": "programare orientata pe obiecte",
    "structuridedate": "structuri de date",
    "sistemedeoperare": "sisteme de operare",
    "algoritmicagrafurilor": "algoritmica grafurilor",
    "limbajeformalesicompilatoare": "limbaje formale si compilatoare",
    "mediisiinstrumentedeprogramare": "medii si instrumente de programare",
    "bazededate": "baze de date",
    "inteligentaartificiala": "inteligenta artificiala",
    "automatecalculabilitatesicomplexitate": "automate, calculabilitate si complexitate",
    "metodeavansatedeprogramare": "metode avansate de programare",
    "reteledecalculatoare": "retele de calculatoare",
    "calculnumeric": "calcul numeric",
    "ingineriesoftware": "inginerie software",
    "interfeteomcalculator": "interfete om-calculator",
    "dezvoltareaaplicatiilorweb": "dezvoltarea aplicatiilor web",
    "practicadespecialitate": "practica de specialitate",
    "managementulproiectelorinformatice": "managementul proiectelor informatice",
    "programareparalelaconcurentasidistribuita": "programare paralela, concurenta si distribuita",
    "probabilitatisistatistica": "probabilitati si statistica",
    "practicapentruelaborarealucrariidelicenta": "practica pentru elaborarea lucrarii de licenta",
    "redactaresicomunicarestiintificasiprofesionala": "redactare si comunicare stiintifica si profesionala",
}


def _remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_for_lookup(text: str) -> str:
    """Normalizează pentru căutare în dicționar — fără diacritice, lowercase, fără spații."""
    text = _remove_diacritics(text.lower())
    text = re.sub(r"\s+", "", text)  # elimină TOATE spațiile
    return text.strip()


def compact_spelled_words_v2(text: str) -> str:
    """
    Versiune îmbunătățită față de cea originală.
    
    Rezolvă două cazuri:
    1. Litere complet izolate: "a l g o r i t m i" → "algoritmi"
       (bufferul de litere singure se unește dacă sunt 3+)
    2. Silabe izolate: "f unda m en t al i" → "fundamentali"
       (token-uri scurte de 1-3 litere consecutive se unesc)
    
    Strategia: dacă mai mult de 50% din token-uri sunt scurte (1-3 litere),
    tratăm tot cuvântul ca OCR distorsionat și unim totul.
    """
    tokens = text.split()
    if not tokens:
        return text

    # Detectăm dacă textul arată ca OCR distorsionat
    short_tokens = sum(1 for t in tokens if len(t) <= 3)
    ratio = short_tokens / len(tokens)

    if ratio >= 0.5 and len(tokens) >= 4:
        # Mod OCR: unim token-urile în grupuri logice
        # Împărțim în "cuvinte" la token-urile mai lungi (>3 litere)
        words: list[str] = []
        buffer: list[str] = []

        for token in tokens:
            if len(token) <= 3:
                buffer.append(token)
            else:
                if buffer:
                    # Unim buffer-ul cu token-ul lung
                    words.append("".join(buffer) + token)
                    buffer = []
                else:
                    words.append(token)

        if buffer:
            words.append("".join(buffer))

        return " ".join(words)

    # Mod normal (original): unim doar secvențe de litere singure (>=3)
    compacted: list[str] = []
    buf: list[str] = []

    for token in tokens:
        if len(token) == 1 and token.isalpha():
            buf.append(token)
            continue
        if buf:
            if len(buf) >= 3:
                compacted.append("".join(buf))
            else:
                compacted.extend(buf)
            buf = []
        compacted.append(token)

    if buf:
        if len(buf) >= 3:
            compacted.append("".join(buf))
        else:
            compacted.extend(buf)

    return " ".join(compacted)


def repair_discipline_name(raw_name: str) -> str:
    """
    Entry point principal — repară numele unei discipline.
    
    Pași:
    1. Lookup direct în dicționarul de nume cunoscute (după ce elimină spațiile)
    2. Aplică compact_spelled_words_v2 pentru reconstrucție automată
    3. Lookup din nou după reconstrucție
    """
    if not raw_name or not raw_name.strip():
        return raw_name

    # Pas 1: lookup direct (cu spații eliminate)
    key = _normalize_for_lookup(raw_name)
    if key in DISCIPLINE_CUNOSCUTE_NORMALIZED:
        return DISCIPLINE_CUNOSCUTE_NORMALIZED[key]

    # Pas 2: reconstrucție automată
    reconstructed = compact_spelled_words_v2(raw_name.strip())

    # Pas 3: lookup după reconstrucție
    key2 = _normalize_for_lookup(reconstructed)
    if key2 in DISCIPLINE_CUNOSCUTE_NORMALIZED:
        return DISCIPLINE_CUNOSCUTE_NORMALIZED[key2]

    return reconstructed