#!/usr/bin/env python3
import sqlite3
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
loaded = load_dotenv(dotenv_path=env_path, verbose=True)

# Seteaza corect calea catre DB (ajustata pentru folderul backend)
DB = Path("backend/data/discipline_new.db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# If still not loaded, try manual parsing
if not GEMINI_API_KEY and env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                GEMINI_API_KEY = line.split("=", 1)[1]
                break

def genereaza_prompt_audit(nume_materie, text_tematica, text_bibliografie):
    prompt = f"""Ești un Auditor Academic AI. Rolul tău este să evaluezi calitatea unei Fișe de Disciplină.

    Materia evaluată: "{nume_materie}"
    
    --- TEMATICĂ CURS ---
    {text_tematica}
    
    --- BIBLIOGRAFIE ---
    {text_bibliografie}
    
    Sarcini:
    1. CONȚINUT VAG: Analizează tematica. Este prea generică? Conține doar termeni precum "Introducere", "Partea 1"? Dacă da, marcheaz-o ca "VAG" și oferă 2 propuneri specifice de îmbunătățire. Dacă e okay, marcheaz-o "DETALIAT".
    2. BIBLIOGRAFIE: Extrage anii din bibliografie. Considerăm anul curent 2026. Dacă nu există NICIUN titlu publicat în ultimii 5 ani (2021-2026), marcheaz-o ca "INVECHITA". Altfel, "ACTUALIZATA".

    Trebuie să răspunzi STRICT în acest format JSON:
    {{
        "audit_tematica": {{
            "status": "VAG" | "DETALIAT",
            "explicatie": "de ce este vag sau detaliat",
            "sugestii_imbunatatire": ["Sugestia 1", "Sugestia 2"]
        }},
        "audit_bibliografie": {{
            "status": "INVECHITA" | "ACTUALIZATA",
            "cel_mai_nou_an_gasit": 2018,
            "explicatie": "motivul deciziei"
        }}
    }}
    """
    return prompt

def ruleaza_audit_pentru_materie(fisa_id: int):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    materie = cur.execute("SELECT nume FROM fisa_discipline WHERE id = ?", (fisa_id,)).fetchone()
    if not materie:
        return
    nume_materie = materie[0]
    
    curs_row = cur.execute("SELECT continut FROM fisa_sectiuni WHERE fisa_id = ? AND tip_sectiune = 'curs'", (fisa_id,)).fetchone()
    biblio_row = cur.execute("SELECT continut FROM fisa_sectiuni WHERE fisa_id = ? AND tip_sectiune = 'bibliografie'", (fisa_id,)).fetchone()
    
    text_curs = curs_row[0] if curs_row else "Nu există tematică."
    text_biblio = biblio_row[0] if biblio_row else "Nu există bibliografie."
    
    conn.close()

    prompt_final = genereaza_prompt_audit(nume_materie, text_curs, text_biblio)
    
    if not GEMINI_API_KEY:
        print(f"[ERROR] GEMINI_API_KEY not set in environment variables.")
        return None
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest')
        response = model.generate_content(prompt_final)
        response_text = response.text
        
        # Extraem JSON din răspuns
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Dacă răspunsul conține text în plus, încercăm să extraem JSON
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"error": "Failed to parse JSON from Gemini response", "raw": response_text}
        
    except Exception as exc:
        print(f"[ERROR] Gemini API call failed: {exc}")
        return None

def ruleaza_audit_complet():
    conn = sqlite3.connect(DB)
    fisa_ids = conn.execute("SELECT id FROM fisa_discipline ORDER BY id").fetchall()
    conn.close()
    
    rezultate = []
    for (fisa_id,) in fisa_ids:
        print(f"\n[*] Auditez disciplina cu id={fisa_id}...")
        rezultat = ruleaza_audit_pentru_materie(fisa_id)
        if rezultat:
            rezultate.append({"fisa_id": fisa_id, **rezultat})
    
    raport_path = Path("backend/data/audit_report.json")
    with open(raport_path, "w", encoding="utf-8") as f:
        json.dump(rezultate, f, ensure_ascii=False, indent=2)
    
    print(f"\n[✓] Raport salvat: {raport_path}")
    return rezultate

if __name__ == "__main__":
    print(f"[DEBUG] GEMINI_API_KEY set: {bool(GEMINI_API_KEY)}")
    print(f"[DEBUG] DB path: {DB}, exists: {DB.exists()}")
    
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        ruleaza_audit_complet()
    else:
        print("[*] Test audit pe discipline din DB...")
        conn = sqlite3.connect(DB)
        first_id = conn.execute("SELECT id FROM fisa_discipline LIMIT 1").fetchone()
        conn.close()
        
        if first_id:
            fisa_id = first_id[0]
            print(f"[*] Auditez disciplina cu id={fisa_id}...")
            rezultat = ruleaza_audit_pentru_materie(fisa_id)
            if rezultat:
                print("[✓] Audit result:")
                print(json.dumps(rezultat, ensure_ascii=False, indent=2))
            else:
                print("[!] Audit failed. Please check your API Key.")
        else:
            print("[!] No disciplines found in DB")