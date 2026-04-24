import json
from typing import Any, Dict, List, Tuple


def _parse_number(v: Any) -> Tuple[bool, float]:
    if v is None:
        return False, 0.0
    if isinstance(v, (int, float)):
        return True, float(v)
    if isinstance(v, str):
        s = v.strip().replace('\u00A0', ' ')
        if s.endswith('%'):
            s = s[:-1].strip()
        try:
            return True, float(s)
        except ValueError:
            return False, 0.0
    return False, 0.0


def _collect_by_keys(obj: Any, key_set: set, out: List[Tuple[str, Any]], path: List[str] = None):
    if path is None:
        path = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in key_set:
                out.append((".".join(path + [k]), v))
            _collect_by_keys(v, key_set, out, path + [k])
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _collect_by_keys(item, key_set, out, path + [f"[{i}]"])


def extract_weights(fd_json: Dict[str, Any]) -> List[Tuple[str, float]]:
    weight_keys = {"ponder", "ponderi", "ponderare", "weight", "procent", "procentaj", "percent"}
    found: List[Tuple[str, Any]] = []
    _collect_by_keys(fd_json, weight_keys, found)

    weights: List[Tuple[str, float]] = []
    for path, raw in found:
        ok, num = _parse_number(raw)
        if ok:
            weights.append((path, num))
        elif isinstance(raw, list):
            for i, item in enumerate(raw):
                ok2, num2 = _parse_number(item)
                if ok2:
                    weights.append((f"{path}[{i}]", num2))
    return weights


def check_weights_sum(weights: List[Tuple[str, float]], tol: float = 1e-6) -> Dict[str, Any]:
    vals = [w for _, w in weights]
    s = sum(vals)
    ok = abs(s - 100.0) <= tol
    return {
        "values": weights,
        "sum": s,
        "ok": ok,
        "difference": s - 100.0,
        "tolerance": tol,
        "alert": None if ok else f"Weights sum to {s} (difference {s-100.0})"
    }


def check_hours(fd_json: Dict[str, Any]) -> Dict[str, Any]:
    hour_keys = {
        "curs": ["ore_curs", "curs", "cursuri"],
        "seminar": ["ore_seminar", "seminar"],
        "laborator": ["ore_laborator", "laborator", "lab"],
        "total": ["total_ore", "ore_total", "total"],
    }

    collected: Dict[str, float] = {k: 0.0 for k in hour_keys}

    def search_hours(obj: Any, path: List[str] = None):
        if path is None:
            path = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = k.lower()
                for label, keys in hour_keys.items():
                    if lk in keys:
                        ok, num = _parse_number(v)
                        if ok:
                            collected[label] = collected.get(label, 0.0) + num
                search_hours(v, path + [k])
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                search_hours(item, path + [f"[{i}]"])

    search_hours(fd_json)

    course = collected.get("curs", 0.0)
    seminar = collected.get("seminar", 0.0)
    lab = collected.get("laborator", 0.0)
    total_decl = collected.get("total", None)
    summed = course + seminar + lab
    ok = True
    alert = None
    if total_decl is None:
        ok = False
        alert = "Declared total hours not found"
    else:
        if abs(summed - total_decl) > 1e-6:
            ok = False
            alert = f"Sum of components {summed} != declared total {total_decl} (diff {summed - total_decl})"

    return {
        "course": course,
        "seminar": seminar,
        "lab": lab,
        "sum_components": summed,
        "declared_total": total_decl,
        "ok": ok,
        "alert": alert,
    }


def check_fd_math(fd_json: Dict[str, Any]) -> Dict[str, Any]:
    weights = extract_weights(fd_json)
    weights_report = check_weights_sum(weights)
    hours_report = check_hours(fd_json)

    report = {
        "report_type": "Math Checker",
        "weights": weights_report,
        "hours": hours_report,
    }
    return report


if __name__ == "__main__":
    sample = {
        "Tabel evaluare": [
            {"component": "Examen final", "ponder": "60%"},
            {"component": "Colocviu", "ponder": "40%"}
        ],
        "Structura ore": {
            "ore_curs": 28,
            "ore_seminar": 7,
            "ore_laborator": 5,
            "total_ore": 40
        }
    }

    out = check_fd_math(sample)
    print(json.dumps(out, ensure_ascii=False, indent=2))