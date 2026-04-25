from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rapidfuzz import fuzz

from pdf_ingestion_service import FisaData, PlanDisciplina
from ocr_name_fix import repair_discipline_name


class Severitate(str, Enum):
    EROARE = "eroare"
    AVERTISMENT = "avertisment"
    OK = "ok"


@dataclass
class RezultatValidare:
    cod_fisa: Optional[str]
    nume_fisa: str
    semestru_fisa: int
    severitate: Severitate
    tip: str
    mesaj: str
    detalii: dict = field(default_factory=dict)
    competente_recomandate: list[str] = field(default_factory=list)


@dataclass
class RaportValidare:
    total_fise: int
    total_discipline_plan: int
    erori: int
    avertismente: int
    ok: int
    rezultate: list[RezultatValidare]

    def to_dict(self) -> dict:
        return {
            "sumar": {
                "total_fise": self.total_fise,
                "total_discipline_plan": self.total_discipline_plan,
                "erori": self.erori,
                "avertismente": self.avertismente,
                "ok": self.ok,
            },
            "rezultate": [
                {
                    "cod_fisa": r.cod_fisa,
                    "nume_fisa": r.nume_fisa,
                    "semestru_fisa": r.semestru_fisa,
                    "severitate": r.severitate.value,
                    "tip": r.tip,
                    "mesaj": r.mesaj,
                    "detalii": r.detalii,
                    "competente_recomandate": r.competente_recomandate,
                }
                for r in self.rezultate
            ],
        }


# ---------------------------------------------------------------------------
# Competente reale din PI — Informatica, UTBv 2024-2027
# Fiecare disciplina e mapata la competentele pe care le dezvolta
# ---------------------------------------------------------------------------
COMPETENTE_PI = [
    {
        "cod": "CP1",
        "nume": "Creează softuri, dezvoltă prototipul pentru software",
        "discipline": [
            "fundamentele programarii",
            "programare orientata pe obiecte",
            "structuri de date",
            "algoritmi fundamentali",
            "algoritmica grafurilor",
            "metode avansate de programare",
            "inginerie software",
            "programare paralela, concurenta si distribuita",
            "dezvoltarea aplicatiilor web",
            "interfete om-calculator",
            "medii si instrumente de programare",
            "limbaje formale si compilatoare",
        ],
    },
    {
        "cod": "CP2",
        "nume": "Utilizează șabloane de proiectare de software, creează diagrama de proces",
        "discipline": [
            "inginerie software",
            "metode avansate de programare",
            "medii si instrumente de programare",
            "limbaje formale si compilatoare",
            "arhitectura sistemelor de calcul",
            "sisteme de operare",
            "managementul proiectelor informatice",
            "programare orientata pe obiecte",
            "dezvoltarea aplicatiilor web",
        ],
    },
    {
        "cod": "CP3",
        "nume": "Analizează specificații software, definește arhitectura software, proiectează sistemul informatic",
        "discipline": [
            "inginerie software",
            "arhitectura sistemelor de calcul",
            "sisteme de operare",
            "retele de calculatoare",
            "baze de date",
            "inteligenta artificiala",
            "automate, calculabilitate si complexitate",
            "managementul proiectelor informatice",
            "probabilitati si statistica",
            "calcul numeric",
            "interfete om-calculator",
            "practica de specialitate",
            "practica pentru elaborarea lucrarii de licenta",
        ],
    },
    {
        "cod": "CT1",
        "nume": "Aplică competente de bază în materie de programare, operează echipamente hardware digitale",
        "discipline": [
            "fundamentele programarii",
            "algoritmi fundamentali",
            "arhitectura sistemelor de calcul",
            "sisteme de operare",
            "retele de calculatoare",
            "fundamentele algebrice ale informaticii",
            "algebra liniara, geometrie analitica si diferentiala",
            "analiza matematica",
            "logica matematica si computationala",
            "notiuni fundamentale de informatica",
            "notiuni fundamentale de matematica",
            "structuri de date",
        ],
    },
    {
        "cod": "CT2",
        "nume": "Utilizează software de comunicare și colaborare, efectuează căutări pe Internet",
        "discipline": [
            "retele de calculatoare",
            "dezvoltarea aplicatiilor web",
            "medii si instrumente de programare",
            "redactare si comunicare stiintifica si profesionala",
            "limba engleza 1",
            "limba engleza 2",
            "limba germana 1",
            "limba germana 2",
            "limba germana 1-2",
            "limba germana 1 2",
        ],
    },
    {
        "cod": "CT3",
        "nume": "Identifică probleme, soluționează probleme",
        "discipline": [
            "algoritmi fundamentali",
            "algoritmica grafurilor",
            "structuri de date",
            "automate, calculabilitate si complexitate",
            "inteligenta artificiala",
            "calcul numeric",
            "probabilitati si statistica",
            "logica matematica si computationala",
            "analiza matematica",
            "algebra liniara, geometrie analitica si diferentiala",
            "fundamentele algebrice ale informaticii",
            "notiuni fundamentale de matematica",
            "notiuni fundamentale de informatica",
        ],
    },
    {
        "cod": "CT4",
        "nume": "Demonstrează angajament, gândește rapid, gândește analitic",
        "discipline": [
            "analiza matematica",
            "algebra liniara, geometrie analitica si diferentiala",
            "fundamentele algebrice ale informaticii",
            "logica matematica si computationala",
            "automate, calculabilitate si complexitate",
            "probabilitati si statistica",
            "calcul numeric",
            "practica de specialitate",
            "practica pentru elaborarea lucrarii de licenta",
            "notiuni fundamentale de matematica",
            "educatie fizica si sport 1",
            "educatie fizica si sport 2",
        ],
    },
    {
        "cod": "CT5",
        "nume": "Lucrează în echipe, organizează informații, obiecte și resurse",
        "discipline": [
            "managementul proiectelor informatice",
            "redactare si comunicare stiintifica si profesionala",
            "practica de specialitate",
            "practica pentru elaborarea lucrarii de licenta",
            "inginerie software",
            "etica si integritate academica i",
            "etica si integritate academica",
            "limba engleza 1",
            "limba engleza 2",
            "limba germana 1",
            "limba germana 2",
            "limba germana 1-2",
            "educatie fizica si sport 1",
            "educatie fizica si sport 2",
        ],
    },
]

SIMILARITY_THRESHOLD = 72

FV_MAP: dict[str, set[str]] = {
    "e":   {"examen", "e", "exam"},
    "c":   {"colocviu", "c", "colocv"},
    "v":   {"verificare", "v", "vp"},
    "a/r": {"admis/respins", "a/r", "ar", "admis", "respins"},
}


def _normalize(text: str) -> str:
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _find_match(fisa: FisaData, plan: list[PlanDisciplina]) -> Optional[PlanDisciplina]:
    # Folosim numele reparat pentru matching
    fisa_cod = _normalize(fisa.cod or "")
    fisa_nume = _normalize(repair_discipline_name(fisa.nume))

    if fisa_cod:
        for p in plan:
            if _normalize(p.cod) == fisa_cod:
                return p

    for p in plan:
        if _normalize(p.nume) == fisa_nume:
            return p

    best_score = 0
    best_match: Optional[PlanDisciplina] = None
    for p in plan:
        score = fuzz.token_sort_ratio(fisa_nume, _normalize(p.nume))
        if score > best_score:
            best_score = score
            best_match = p

    if best_score >= SIMILARITY_THRESHOLD:
        return best_match

    return None


def _recomanda_competente(nume_disciplina: str) -> list[str]:
    """
    Returnează competentele CP1-CP3, CT1-CT5 relevante pentru o disciplina,
    bazat pe mapping-ul explicit din PI.
    Foloseste numele reparat (fara distorsiuni OCR).
    """
    nume_reparat = repair_discipline_name(nume_disciplina)
    nume_norm = _normalize(nume_reparat)
    rezultat: list[str] = []

    for comp in COMPETENTE_PI:
        for disc in comp["discipline"]:
            disc_norm = _normalize(disc)
            if disc_norm == nume_norm:
                rezultat.append(f"{comp['cod']}: {comp['nume']}")
                break
            score = fuzz.token_sort_ratio(nume_norm, disc_norm)
            if score >= 82:
                rezultat.append(f"{comp['cod']}: {comp['nume']}")
                break

    return rezultat


def recomanda_competente(nume_disciplina: str) -> list[str]:
    """
    Public helper used by API endpoints to fetch recommended competencies
    for a single subject name.
    """
    return _recomanda_competente(nume_disciplina)


def list_discipline_competente() -> list[str]:
    """
    Returns distinct subject names known by the PI competency map.
    """
    seen: set[str] = set()
    subjects: list[str] = []

    for comp in COMPETENTE_PI:
        for disc in comp["discipline"]:
            norm = _normalize(disc)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            subjects.append(disc)

    subjects.sort(key=_normalize)
    return subjects


def valideaza_nivel2(fise: list[FisaData], plan: list[PlanDisciplina]) -> RaportValidare:
    rezultate: list[RezultatValidare] = []

    for fisa in fise:
        # Reparăm numele înainte de orice operație
        nume_reparat = repair_discipline_name(fisa.nume)
        fisa_display = fisa
        # Cream o copie cu numele reparat pentru afisare
        fisa_display_nume = nume_reparat

        match = _find_match(fisa, plan)
        competente = _recomanda_competente(fisa.nume)

        if match is None:
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa_display_nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.EROARE,
                tip="fisa_negasita_in_plan",
                mesaj=f"Disciplina '{fisa_display_nume}' nu a fost gasita in Planul de Invatamant.",
                detalii={"cod_cautat": fisa.cod},
                competente_recomandate=competente,
            ))
            continue

        # Colectăm toate problemele găsite pentru această disciplină
        probleme: list[str] = []
        detalii_combinate: dict = {"cod_plan": match.cod}
        severitate_max = Severitate.OK

        if fisa.credite != match.credite:
            probleme.append(f"credite diferite: FD={fisa.credite}, PI={match.credite}")
            detalii_combinate["credite_fisa"] = fisa.credite
            detalii_combinate["credite_plan"] = match.credite
            severitate_max = Severitate.EROARE

        if fisa.semestru != match.semestru:
            probleme.append(f"semestru diferit: FD={fisa.semestru}, PI={match.semestru}")
            detalii_combinate["semestru_fisa"] = fisa.semestru
            detalii_combinate["semestru_plan"] = match.semestru
            severitate_max = Severitate.EROARE

        similarity = fuzz.token_sort_ratio(_normalize(fisa_display_nume), _normalize(match.nume))
        if SIMILARITY_THRESHOLD <= similarity < 95:
            probleme.append(f"nume similar dar nu identic cu '{match.nume}' (similaritate {similarity}%)")
            detalii_combinate["similaritate_procent"] = similarity
            detalii_combinate["nume_plan"] = match.nume
            if severitate_max == Severitate.OK:
                severitate_max = Severitate.AVERTISMENT

        if not probleme:
            # Totul OK
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa_display_nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.OK,
                tip="ok",
                mesaj=f"'{fisa_display_nume}' — toate campurile coincid cu PI.",
                detalii={"cod_plan": match.cod},
                competente_recomandate=competente,
            ))
        else:
            # Un singur rezultat cu toate problemele combinate
            tip = "erori_multiple" if len(probleme) > 1 else (
                "credite_diferite" if "credite" in probleme[0] else
                "semestru_diferit" if "semestru" in probleme[0] else
                "nume_similar_nu_identic"
            )
            mesaj = f"'{fisa_display_nume}': " + "; ".join(probleme) + "."
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa_display_nume,
                semestru_fisa=fisa.semestru,
                severitate=severitate_max,
                tip=tip,
                mesaj=mesaj,
                detalii=detalii_combinate,
                competente_recomandate=competente,
            ))

    # Discipline din PI fara FD
    fise_nume_norm = {_normalize(repair_discipline_name(f.nume)) for f in fise}
    fise_cod_norm = {_normalize(f.cod or "") for f in fise}

    for p in plan:
        p_nume = _normalize(p.nume)
        p_cod = _normalize(p.cod)
        matched_by_name = any(
            fuzz.token_sort_ratio(p_nume, fn) >= SIMILARITY_THRESHOLD
            for fn in fise_nume_norm
        )
        matched_by_cod = p_cod in fise_cod_norm and p_cod != ""
        if not matched_by_name and not matched_by_cod:
            rezultate.append(RezultatValidare(
                cod_fisa=None,
                nume_fisa=p.nume,
                semestru_fisa=p.semestru,
                severitate=Severitate.AVERTISMENT,
                tip="disciplina_plan_fara_fisa",
                mesaj=f"Disciplina '{p.nume}' (cod: {p.cod}) exista in PI dar nu are Fisa de Disciplina.",
                detalii={"cod_plan": p.cod, "credite_plan": p.credite},
                competente_recomandate=_recomanda_competente(p.nume),
            ))

    erori = sum(1 for r in rezultate if r.severitate == Severitate.EROARE)
    avertismente = sum(1 for r in rezultate if r.severitate == Severitate.AVERTISMENT)
    ok = sum(1 for r in rezultate if r.severitate == Severitate.OK)

    return RaportValidare(
        total_fise=len(fise),
        total_discipline_plan=len(plan),
        erori=erori,
        avertismente=avertismente,
        ok=ok,
        rezultate=rezultate,
    )
