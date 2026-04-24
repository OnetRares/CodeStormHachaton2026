import json
from typing import Dict, Any, Optional


def generate_fisa_template(plan: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Populate a Fisa_Disciplina template from a Plan_Invatamant record.

    Rules:
    - `nume_disciplina` <- plan['nume_disciplina']
    - `credite` <- plan['credite']
    - `evaluare.tip` <- plan['forma_verificare'] (e.g. 'E' or 'C')
    - All other fields are kept present but set to None (or empty list where appropriate).

    Returns the populated template dict (does not modify the input `plan`).
    """
    out: Dict[str, Any] = {} if template is None else dict(template)

    # Basic top-level fields
    out["nume_disciplina"] = plan.get("nume_disciplina")
    out["semestru"] = out.get("semestru") if out.get("semestru") is not None else None
    out["credite"] = plan.get("credite")

    # Evaluare: ensure object exists, set tip from plan, leave ponderi as empty list
    ev = out.get("evaluare") if isinstance(out.get("evaluare"), dict) else {}
    ev["tip"] = plan.get("forma_verificare") or ev.get("tip")
    # leave ponderi_curs_laborator empty (caller can fill)
    ev["ponderi_curs_laborator"] = ev.get("ponderi_curs_laborator") if ev.get("ponderi_curs_laborator") is not None else []
    out["evaluare"] = ev

    # Ore: keep structure but set numeric fields to None if not present
    ore = out.get("ore") if isinstance(out.get("ore"), dict) else {}
    ore.setdefault("total_plan", None)
    ore.setdefault("curs", None)
    ore.setdefault("laborator", None)
    out["ore"] = ore

    # Example of other optional fields commonly in a working sheet
    # Set them to None to indicate they need completion (bibliografia, obiective, continut)
    optional_fields = ["bibliografia", "obiective", "continut", "observatii"]
    for f in optional_fields:
        out.setdefault(f, None)

    return out


if __name__ == "__main__":
    # quick demo
    sample_plan = {
        "cod_disciplina": "CS101",
        "nume_disciplina": "Algoritmi",
        "ore_curs": 28,
        "forma_verificare": "E",
        "credite": 6
    }
    template = {}
    filled = generate_fisa_template(sample_plan, template)
    print(json.dumps(filled, ensure_ascii=False, indent=2))
