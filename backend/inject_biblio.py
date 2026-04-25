#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB = Path("backend/data/discipline_new.db")

def inject_bibliografie():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    fisa_ids = [r[0] for r in cur.execute("SELECT id FROM fisa_discipline LIMIT 2").fetchall()]
    
    # Adăugăm o bibliografie VECHE (Eroare Nivel 3)
    cur.execute("INSERT INTO fisa_sectiuni (fisa_id, tip_sectiune, continut) VALUES (?, ?, ?)",
                (fisa_ids[0], "bibliografie", "1. I.D. Ion - Probleme de algebra, EDP 1981.\n2. C. Szasz - Curs de algebra, Brasov 1978."))
    
    # Adăugăm o bibliografie NOUĂ (Corectă)
    cur.execute("INSERT INTO fisa_sectiuni (fisa_id, tip_sectiune, continut) VALUES (?, ?, ?)",
                (fisa_ids[1], "bibliografie", "1. F.L. Tiplea - Fundamente, 2006.\n2. Modern Machine Learning, O'Reilly 2023."))
    
    conn.commit()
    conn.close()
    print("Bibliografiile de test au fost adaugate!")

if __name__ == "__main__":
    inject_bibliografie()