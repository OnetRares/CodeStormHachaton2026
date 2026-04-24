from typing import Dict, Any, List


class ConflictError(Exception):
    """Raised when cross-document conflicts are found.

    The exception message includes human-readable details about each conflict.
    """
    def __init__(self, messages: List[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


def compare_documents(fd_json: Dict[str, Any], pi_json: Dict[str, Any]) -> Dict[str, Any]:
    """Validate cross-document conformity between a Fisa_Disciplina (`fd_json`) and a Plan_Invatamant (`pi_json`).

    Rules checked strictly:
    - `fd_json['credite']` must equal `pi_json['credite']`
    - `fd_json['evaluare']['tip']` must match `pi_json['forma_verificare']`

    If conflicts exist, raises ConflictError with detailed messages like:
      "Conflict: Planul cere X, dar Fișa conține Y"

    Returns a dict {'ok': True} if no conflicts are found.
    """
    conflicts: List[str] = []

    # credite
    pi_cred = pi_json.get('credite')
    fd_cred = fd_json.get('credite')
    if pi_cred is None:
        conflicts.append("Conflict: Planul nu conține câmpul 'credite'")
    elif fd_cred is None:
        conflicts.append("Conflict: Fișa nu conține câmpul 'credite'")
    elif int(pi_cred) != int(fd_cred):
        conflicts.append(f"Conflict: Planul cere {pi_cred} credite, dar Fișa conține {fd_cred}")

    # forma / evaluare.tip
    pi_forma = pi_json.get('forma_verificare')
    fd_evaluare = fd_json.get('evaluare') or {}
    fd_tip = fd_evaluare.get('tip') if isinstance(fd_evaluare, dict) else None

    if pi_forma is None:
        conflicts.append("Conflict: Planul nu conține câmpul 'forma_verificare'")
    elif fd_tip is None:
        conflicts.append("Conflict: Fișa nu conține câmpul 'evaluare.tip'")
    else:
        # compare as strings (case-insensitive)
        if str(pi_forma).strip().upper() != str(fd_tip).strip().upper():
            conflicts.append(f"Conflict: Planul cere forma '{pi_forma}', dar Fișa conține '{fd_tip}'")

    if conflicts:
        raise ConflictError(conflicts)

    return {'ok': True}


if __name__ == '__main__':
    # quick manual demo
    pi = {'cod_disciplina': 'CS101', 'nume_disciplina': 'Algoritmi', 'ore_curs': 28, 'forma_verificare': 'E', 'credite': 6}
    fd = {'nume_disciplina': 'Algoritmi', 'semestru': 1, 'credite': 5, 'evaluare': {'tip': 'C', 'ponderi_curs_laborator': [50,50]}, 'ore': {'total_plan': 42, 'curs': 28, 'laborator': 14}}
    try:
        print(compare_documents(fd, pi))
    except ConflictError as e:
        print('Conflicts found:')
        for m in e.messages:
            print(' -', m)
