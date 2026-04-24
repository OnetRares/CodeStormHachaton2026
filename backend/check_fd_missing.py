import json
from typing import Any, Dict, List


def _collect_empty_paths(value: Any, path: List[str], out: List[str]) -> None:
    if isinstance(value, dict):
        if not value:
            out.append(".".join(path) if path else "<section_empty_dict>")
            return
        for k, v in value.items():
            _collect_empty_paths(v, path + [k], out)
    elif isinstance(value, list):
        if not value:
            out.append((".".join(path) + "[]") if path else "<section_empty_list>")
            return
        for i, v in enumerate(value):
            if isinstance(v, (dict, list)):
                _collect_empty_paths(v, path + [f"[{i}]"], out)
            else:
                if v is None:
                    out.append(".".join(path + [f"[{i}]"]))
                elif isinstance(v, str) and not v.strip():
                    out.append(".".join(path + [f"[{i}]"]))
    else:
        if value is None:
            out.append(".".join(path) if path else "<section_none>")
        elif isinstance(value, str) and not value.strip():
            out.append(".".join(path) if path else "<section_empty_string>")


def check_fd_missing_fields(fd_json: Dict[str, Any], required_sections: List[str] = None) -> Dict[str, Any]:
    """
    Primește un obiect JSON (ca dict Python) extras dintr-o Fișă a Disciplinei (FD)
    și verifică dacă secțiunile obligatorii sunt prezente și au conținut.

    Secțiunile obligatorii implicite sunt: "Bibliografie", "Metode de evaluare", "Semnături".

    Returnează un raport de tip 'Missing Values' cu structura:
    {
      "report_type": "Missing Values",
      "has_missing": True|False,
      "missing": {
         "Bibliografie": ["references", "notes"],   # listă de căi relative goale
         "Metode de evaluare": ["<section missing>"]
      }
    }

    Căile sunt separate cu punct (.); pentru liste se adaugă sufixul [] sau indexul [i].
    """
    if required_sections is None:
        required_sections = ["Bibliografie", "Metode de evaluare", "Semnături"]

    report: Dict[str, Any] = {"report_type": "Missing Values", "has_missing": False, "missing": {}}

    for sec in required_sections:
        if sec not in fd_json:
            report["missing"][sec] = ["<section_missing>"]
            report["has_missing"] = True
            continue

        value = fd_json.get(sec)
        if value is None:
            report["missing"][sec] = ["<section_null>"]
            report["has_missing"] = True
            continue

        empties: List[str] = []
        _collect_empty_paths(value, [], empties)

        if empties:
            report["missing"][sec] = empties
            report["has_missing"] = True

    return report


if __name__ == "__main__":
    sample_fd = {
        "Denumire": "Programare",
        "Bibliografie": {
            "cursuri": ["  ", "Ion Popescu"],
            "referinte": []
        },
        "Metode de evaluare": " ",
        # "Semnături" missing on purpose
    }

    res = check_fd_missing_fields(sample_fd)
    print(json.dumps(res, ensure_ascii=False, indent=2))