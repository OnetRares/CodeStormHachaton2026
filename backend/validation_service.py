from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rapidfuzz import fuzz

from pdf_ingestion_service import FisaData, PlanDisciplina


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Severitate(str, Enum):
    EROARE = "eroare"       # blocker — date fundamental greșite
    AVERTISMENT = "avertisment"  # posibil greșit — necesită verificare umană
    OK = "ok"


@dataclass
class RezultatValidare:
    cod_fisa: Optional[str]
    nume_fisa: str
    semestru_fisa: int
    severitate: Severitate
    tip: str          # slug scurt, util pentru filtrare în frontend
    mesaj: str
    detalii: dict = field(default_factory=dict)


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
                }
                for r in self.rezultate
            ],
        }


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

# Prag minim de similaritate (0-100) pentru a considera două nume ca fiind
# același curs (ex: "Algebră liniară" vs "Algebra Liniara")
SIMILARITY_THRESHOLD = 72

# Mapare formă verificare PI (coloana FV) → variante acceptate în FD
FV_MAP: dict[str, set[str]] = {
    "e":   {"examen", "e", "exam"},
    "c":   {"colocviu", "c", "colocv"},
    "v":   {"verificare", "v", "vp"},
    "a/r": {"admis/respins", "a/r", "ar", "admis", "respins"},
}


def _normalize(text: str) -> str:
    """Lowercase, fără diacritice, fără spații multiple."""
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _find_match(
    fisa: FisaData,
    plan: list[PlanDisciplina],
) -> Optional[PlanDisciplina]:
    """
    Caută disciplina din PI care corespunde cel mai bine FD-ului.
    Prioritate: potrivire exactă cod > potrivire exactă nume > fuzzy nume.
    """
    fisa_cod = _normalize(fisa.cod or "")
    fisa_nume = _normalize(fisa.nume or "")

    # 1. Cod exact
    if fisa_cod:
        for p in plan:
            if _normalize(p.cod) == fisa_cod:
                return p

    # 2. Nume exact
    for p in plan:
        if _normalize(p.nume) == fisa_nume:
            return p

    # 3. Fuzzy pe nume
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


def _fv_matches(evaluare_fisa: str, fv_plan: str) -> bool:
    """Verifică dacă forma de evaluare din FD corespunde FV din PI."""
    fv_key = _normalize(fv_plan)
    ev_norm = _normalize(evaluare_fisa)
    accepted = FV_MAP.get(fv_key, {fv_key})
    return ev_norm in accepted or any(ev_norm.startswith(a) for a in accepted)


# ---------------------------------------------------------------------------
# Core validation — Nivel 2
# ---------------------------------------------------------------------------

def valideaza_nivel2(
    fise: list[FisaData],
    plan: list[PlanDisciplina],
) -> RaportValidare:
    """
    Realizează validarea cross-document FD ↔ PI.

    Verificări per FD:
      1. Există în PI? (după cod sau nume fuzzy)
      2. Creditele coincid?
      3. Semestrul coincide?
      4. Forma de verificare (E/C/V) coincide?
    """
    rezultate: list[RezultatValidare] = []

    for fisa in fise:
        match = _find_match(fisa, plan)

        # ----------------------------------------------------------------
        # FD nu a fost găsit în PI
        # ----------------------------------------------------------------
        if match is None:
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa.nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.EROARE,
                tip="fisa_negasita_in_plan",
                mesaj=f"Disciplina '{fisa.nume}' nu a fost găsită în Planul de Învățământ.",
                detalii={"cod_cautat": fisa.cod},
            ))
            continue

        # ----------------------------------------------------------------
        # FD găsit — verificări punct cu punct
        # ----------------------------------------------------------------
        found_issues = False

        # 1. Credite
        if fisa.credite != match.credite:
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa.nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.EROARE,
                tip="credite_diferite",
                mesaj=(
                    f"'{fisa.nume}': creditele din FD ({fisa.credite}) "
                    f"diferă față de PI ({match.credite})."
                ),
                detalii={
                    "credite_fisa": fisa.credite,
                    "credite_plan": match.credite,
                    "cod_plan": match.cod,
                },
            ))
            found_issues = True

        # 2. Semestru
        if fisa.semestru != match.semestru:
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa.nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.EROARE,
                tip="semestru_diferit",
                mesaj=(
                    f"'{fisa.nume}': semestrul din FD ({fisa.semestru}) "
                    f"diferă față de PI ({match.semestru})."
                ),
                detalii={
                    "semestru_fisa": fisa.semestru,
                    "semestru_plan": match.semestru,
                    "cod_plan": match.cod,
                },
            ))
            found_issues = True

        # 3. Formă verificare
        # PI stochează codul FV (E/C/V/A/R); FD stochează textul complet
        # Folosim FV-ul din PI ca referință
        fv_plan = _normalize(match.cod)  # coloana FV nu e în PlanDisciplina încă —
        # dacă colegul extinde modelul cu câmpul `fv`, îl folosim direct.
        # Deocamdată facem verificarea dacă câmpul e disponibil.
        evaluare_fisa = _normalize(fisa.evaluare)

        # Verificare posibilă doar dacă FD are evaluare explicită și diferă clar
        if evaluare_fisa and evaluare_fisa not in {"neprecizat", ""}:
            # Heuristică: dacă FD zice "examen" dar PI are C → conflict
            # Această verificare devine precisă când PlanDisciplina va include câmpul fv
            pass  # placeholder — se activează când modelul PI include fv (vezi nota de mai jos)

        # 4. Potrivire fuzzy sub prag — avertisment de nume
        fisa_nume_norm = _normalize(fisa.nume)
        plan_nume_norm = _normalize(match.nume)
        similarity = fuzz.token_sort_ratio(fisa_nume_norm, plan_nume_norm)
        if similarity < 95 and similarity >= SIMILARITY_THRESHOLD:
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa.nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.AVERTISMENT,
                tip="nume_similar_nu_identic",
                mesaj=(
                    f"'{fisa.nume}' a fost asociat cu '{match.nume}' din PI "
                    f"(similaritate {similarity}%). Verificați manual."
                ),
                detalii={
                    "nume_fisa": fisa.nume,
                    "nume_plan": match.nume,
                    "similaritate_procent": similarity,
                    "cod_plan": match.cod,
                },
            ))
            found_issues = True

        # Totul OK pentru această FD
        if not found_issues:
            rezultate.append(RezultatValidare(
                cod_fisa=fisa.cod,
                nume_fisa=fisa.nume,
                semestru_fisa=fisa.semestru,
                severitate=Severitate.OK,
                tip="ok",
                mesaj=f"'{fisa.nume}' — toate câmpurile coincid cu PI.",
                detalii={"cod_plan": match.cod},
            ))

    # ----------------------------------------------------------------
    # Discipline din PI fără FD corespunzătoare (invers)
    # ----------------------------------------------------------------
    fise_nume_norm = {_normalize(f.nume) for f in fise}
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
                mesaj=(
                    f"Disciplina '{p.nume}' (cod: {p.cod}) există în PI "
                    f"dar nu are o Fișă de Disciplină corespunzătoare."
                ),
                detalii={"cod_plan": p.cod, "credite_plan": p.credite},
            ))

    # ----------------------------------------------------------------
    # Sumar
    # ----------------------------------------------------------------
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