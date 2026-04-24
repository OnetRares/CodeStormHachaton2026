from typing import Any, Dict, List


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
        """Return list of keys (dot notation) that are null/empty.

        - Considers empty string, None, or empty list as missing.
        - Checks the canonical Fisa_Disciplina structure.
        """
        missing: List[str] = []

        def empty(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str) and val.strip() == "":
                return True
            if isinstance(val, (list, tuple)) and len(val) == 0:
                return True
            return False

        # top-level fields
        for key in ("nume_disciplina", "semestru", "credite"):
            v = self.data.get(key)
            if empty(v):
                missing.append(key)

        # evaluare
        ev = self.data.get("evaluare")
        if ev is None:
            missing.append("evaluare")
        else:
            if empty(ev.get("tip")):
                missing.append("evaluare.tip")
            if empty(ev.get("ponderi_curs_laborator")):
                missing.append("evaluare.ponderi_curs_laborator")

        # ore
        ore = self.data.get("ore")
        if ore is None:
            missing.append("ore")
        else:
            for sub in ("total_plan", "curs", "laborator"):
                if empty(ore.get(sub)):
                    missing.append(f"ore.{sub}")

        return missing

    def check_math(self) -> Dict[str, str]:
        """Return a dict with math/integrity errors found.

        Keys:
        - 'ponderi' => error about weights sum or malformed values
        - 'ore' => error about hours sum or malformed values
        Returns empty dict when no errors.
        """
        errors: Dict[str, str] = {}

        # Check weights sum == 100
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

        # Check ore.curs + ore.laborator == ore.total_plan
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
                        errors["ore"] = f"curs + laborator = {int(c) + int(l)}, expected total_plan {int(tp)}"
                except Exception:
                    errors["ore"] = "ore fields contain non-integer values"

        return errors


if __name__ == "__main__":
    # small local demo when run directly
    sample = {
        "nume_disciplina": "Algoritmi",
        "semestru": 1,
        "credite": 6,
        "evaluare": {"tip": "E", "ponderi_curs_laborator": [50, 50]},
        "ore": {"total_plan": 42, "curs": 28, "laborator": 14}
    }
    v = ValidatorFD(sample)
    print("Missing:", v.check_missing_fields())
    print("Math errors:", v.check_math())
