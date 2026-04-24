#!/usr/bin/env python3
import pypdf
import re
import json

def verifica_campuri_pdf(cale_pdf: str) -> dict:
    raport = {
        "fisier": cale_pdf,
        "campuri_lipsa_sau_goale": [],
        "status": "Incomplet"
    }
    
    # 1. Extragem textul brut din PDF folosind noul 'pypdf'
    try:
        with open(cale_pdf, 'rb') as file:
            reader = pypdf.PdfReader(file)
            text_complet = ""
            for page in reader.pages:
                text_extras = page.extract_text()
                if text_extras:
                    text_complet += text_extras + "\n"
    except FileNotFoundError:
        return {"eroare": f"Fisierul {cale_pdf} nu a fost gasit!"}

    # ==========================================
    # REGULI DE VALIDARE (UC 1.1 - The Missing Fields Checker)
    # ==========================================

    # Regula 1: Verificăm Titularul de Curs (Secțiunea 2.2)
    match_titular = re.search(r'2\.2 Titularul activităților de curs(.*?)(?:2\.3 Titularul)', text_complet, re.DOTALL | re.IGNORECASE)
    if match_titular:
        continut_titular = match_titular.group(1).strip()
        if len(continut_titular) < 5: 
            raport["campuri_lipsa_sau_goale"].append("Secțiunea '2.2 Titularul activităților de curs' este necompletată.")
    else:
        raport["campuri_lipsa_sau_goale"].append("Secțiunea '2.2 Titularul activităților de curs' lipsește cu desăvârșire.")

    # Regula 2: Verificăm dacă a completat Bibliografia
    match_biblio = re.search(r'Bibliografie(.*?)(?:9\.\s*Coroborarea)', text_complet, re.DOTALL | re.IGNORECASE)
    if match_biblio:
        continut_biblio = match_biblio.group(1).strip()
        if len(continut_biblio) < 20:
            raport["campuri_lipsa_sau_goale"].append("Secțiunea 'Bibliografie' pare a fi lăsată goală.")
    else:
        raport["campuri_lipsa_sau_goale"].append("Nu am putut detecta secțiunea 'Bibliografie'.")

    # Regula 3: Verificăm dacă există Semnături la final
    if "Decan" not in text_complet or "Titular de curs" not in text_complet:
         raport["campuri_lipsa_sau_goale"].append("Secțiunea de 'Semnături / Avizare' (Decan, Titular) este incompletă sau lipsește.")

    # Regula 4: Verificăm Tipul de Evaluare (Secțiunea 2.6)
    match_evaluare = re.search(r'2\.6 Tipul de evaluare(.*?)(?:2\.7 Regimul)', text_complet, re.DOTALL | re.IGNORECASE)
    if match_evaluare:
        continut_eval = match_evaluare.group(1).strip()
        if len(continut_eval) < 1:
            raport["campuri_lipsa_sau_goale"].append("Secțiunea '2.6 Tipul de evaluare' este necompletată.")

    # Status final
    if len(raport["campuri_lipsa_sau_goale"]) == 0:
        raport["status"] = "Valid - Toate campurile esentiale sunt completate"

    return raport

if __name__ == "__main__":
    from pathlib import Path
    
    # Aflăm folderul unde se află ACEST script (ex: folderul 'backend')
    director_curent = Path(__file__).parent
    
    # Construim calea exactă. 
    # Dacă folderul 'pdf' este în același folder cu scriptul:
    cale_fisier = director_curent / "pdf" / "fisa_disciplina.pdf"
    
    # Dacă folderul 'pdf' e cu un nivel mai sus (în rădăcina proiectului):
    # cale_fisier = director_curent.parent / "pdf" / "fisa_disciplina.pdf"

    print(f"Caut fisierul la calea absoluta: {cale_fisier.absolute()}")
    
    rezultat = verifica_campuri_pdf(str(cale_fisier))
    
    print("\n=== RAPORT DE VALIDARE STRUCTURALĂ PDF (UC 1.1) ===")
    print(json.dumps(rezultat, indent=2, ensure_ascii=False))