#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB_PATH = Path("backend/data/discipline_new.db")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_discipline (
            cod TEXT NOT NULL,
            nume TEXT NOT NULL,
            semestru INTEGER NOT NULL CHECK (semestru IN (1, 2)),
            credite INTEGER NOT NULL CHECK (credite > 0)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fisa_discipline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cod TEXT,
            nume TEXT NOT NULL,
            semestru INTEGER NOT NULL CHECK (semestru IN (1, 2)),
            credite INTEGER NOT NULL CHECK (credite > 0),
            evaluare_format TEXT,
            ore_saptamana INTEGER,
            total_ore_plan INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fisa_sectiuni (
            fisa_id INTEGER NOT NULL,
            tip_sectiune TEXT NOT NULL,
            continut TEXT NOT NULL,
            FOREIGN KEY (fisa_id) REFERENCES fisa_discipline(id) ON DELETE CASCADE
        )
        """
    )


def clear_data(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM fisa_sectiuni")
    cur.execute("DELETE FROM fisa_discipline")
    cur.execute("DELETE FROM plan_discipline")
    cur.execute("DELETE FROM sqlite_sequence WHERE name = 'fisa_discipline'")
    conn.commit()


def populate(conn: sqlite3.Connection) -> dict:
    # sample data chosen to cover evaluation types and sections
    # Date extinse pentru Planul de Învățământ
    plans = [
        ("MAT101", "Analiza Matematica", 1, 5),
        ("CS101", "Fundamentele algebrice ale informaticii", 1, 6),
        ("FIZ201", "Algoritmi fundamentali", 2, 4),
        ("PRJ301", "Fundamentele programarii", 2, 3),
        ("SDD512", "Structuri de date", 1, 2),
        ("SDO215", "Sisteme de operare", 1, 2),
        ("ENG105", "Engleza", 1, 2),
        
        # --- Date noi adăugate ---
        ("POO201", "Programare Orientata pe Obiecte", 1, 6),
        ("BD202", "Baze de Date", 2, 6),
        ("LFA203", "Limbaje Formale si Automate", 2, 5),
        ("AC204", "Arhitectura Calculatoarelor", 1, 5),
        ("RC301", "Retele de Calculatoare", 1, 5),
        ("TW302", "Tehnologii Web", 2, 4),
        ("IA303", "Inteligenta Artificiala", 1, 6),
        ("IP304", "Ingineria Programarii", 2, 5),
        ("GC401", "Grafica pe Calculator", 1, 4),
        ("SEC402", "Securitatea Sistemelor Informatice", 2, 5),
        ("OPT403", "Dezvoltarea Aplicatiilor Mobile (Optional)", 2, 4),
        ("PRJ404", "Proiect de Licenta", 2, 10),
    ]

    # Date extinse pentru Fișele Disciplinei
    plans = [
        ("MAT101", "Analiza Matematica", 1, 5),
        ("CS101", "Fundamentele algebrice ale informaticii", 1, 6),
        ("FIZ201", "Algoritmi fundamentali", 2, 4),
        ("PRJ301", "Fundamentele programarii", 2, 3),
        ("SDD512", "Structuri de date", 1, 2),
        ("SDO215", "Sisteme de operare", 1, 2),
        ("ENG105", "Engleza", 1, 2),
        ("POO201", "Programare Orientata pe Obiecte", 1, 6),
        ("BD202", "Baze de Date", 2, 6),
        ("LFA203", "Limbaje Formale si Automate", 2, 5),
        ("AC204", "Arhitectura Calculatoarelor", 1, 5),
        ("RC301", "Retele de Calculatoare", 1, 5),
        ("TW302", "Tehnologii Web", 2, 4),
        ("IA303", "Inteligenta Artificiala", 1, 6),
        ("IP304", "Ingineria Programarii", 2, 5),
        ("GC401", "Grafica pe Calculator", 1, 4),
        ("SEC402", "Securitatea Sistemelor Informatice", 2, 5),
        ("OPT403", "Dezvoltarea Aplicatiilor Mobile (Optional)", 2, 4),
        ("PRJ404", "Proiect de Licenta", 2, 10),
    ]

    fise = [
        # cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan
        ("MAT101", "Analiza Matematica", 1, 5, "E", 4, 56),
        ("CS101", "Fundamentele algebrice ale informaticii", 1, 6, "C", 3, 42),
        ("FIZ201", "Algoritmi fundamentali", 2, 4, "E", 2, 28),
        ("PRJ301", "Fundamentele programarii", 2, 3, "V", 1, 14),
        ("SDD512", "Structuri de date", 1, 2, "C", 1, 14),
        ("SDO215", "Sisteme de operare", 1, 2, "E", 2, 28),
        ("ENG105", "Engleza", 1, 2, "V", 1, 14),
        ("POO201", "Programare Orientata pe Obiecte", 1, 6, "E", 4, 56),
        ("BD202", "Baze de Date", 2, 6, "E", 4, 56),
        ("LFA203", "Limbaje Formale si Automate", 2, 5, "E", 3, 42),
        ("AC204", "Arhitectura Calculatoarelor", 1, 5, "C", 3, 42),
        ("RC301", "Retele de Calculatoare", 1, 5, "E", 3, 42),
        ("TW302", "Tehnologii Web", 2, 4, "C", 3, 42),
        ("IA303", "Inteligenta Artificiala", 1, 6, "E", 4, 56),
        ("IP304", "Ingineria Programarii", 2, 5, "E", 4, 56),
        ("GC401", "Grafica pe Calculator", 1, 4, "C", 3, 42),
        ("SEC402", "Securitatea Sistemelor Informatice", 2, 5, "E", 3, 42),
        ("OPT403", "Dezvoltarea Aplicatiilor Mobile (Optional)", 2, 4, "V", 3, 42),
        ("PRJ404", "Proiect de Licenta", 2, 10, "C", 4, 56),
    ]

    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO plan_discipline (cod, nume, semestru, credite) VALUES (?, ?, ?, ?)",
        plans,
    )

    fisa_ids = []
    for item in fise:
        cur.execute(
            "INSERT INTO fisa_discipline (cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan) VALUES (?, ?, ?, ?, ?, ?, ?)",
            item,
        )
        fisa_ids.append(cur.lastrowid)

    # add multiple section types per fisa
    sections = []
    for fid, f in zip(fisa_ids, fise):
        cod = f[0]
        sections.append((fid, "descriere", f"Descriere pentru {cod}."))
        sections.append((fid, "curs", f"Tematica curs pentru {cod} (sintetica)."))
        sections.append((fid, "laborator", f"Exercitii si laborator pentru {cod}.") )
        if f[3] >= 3:
            sections.append((fid, "proiect", f"Proiect/tema pentru {cod}."))

    cur.executemany(
        "INSERT INTO fisa_sectiuni (fisa_id, tip_sectiune, continut) VALUES (?, ?, ?)",
        sections,
    )

    conn.commit()
    return {
        "plan_rows": len(plans),
        "fisa_rows": len(fise),
        "sectiuni_rows": len(sections),
    }


def inspect(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    counts = {}
    for t in tables:
        try:
            counts[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            counts[t] = None
    sample = [list(r) for r in cur.execute("SELECT id, cod, nume, semestru, credite, evaluare_format, ore_saptamana, total_ore_plan FROM fisa_discipline LIMIT 5").fetchall()]
    return {"tables": tables, "counts": counts, "sample_fisa": sample}


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        ensure_schema(conn)
        clear_data(conn)
        result = populate(conn)
        summary = inspect(conn)
    print(json.dumps({"status": "populated", "result": result, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
