#!/usr/bin/env python3
import os
import json
import time
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI

# Încărcăm variabilele de mediu
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("[ERROR] Nu am găsit OPENAI_API_KEY în .env!")
else:
    # Inițializăm clientul OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

def genereaza_text_copilot(nume_materie: str, sectiune_fisa: str, notite_profesor: str) -> dict:
    prompt = f"""Ești un Asistent Universitar Expert (Copilot).
    Rolul tău este să ajuți un profesor să completeze o secțiune din "Fișa Disciplinei" folosind un limbaj academic, profesional și la obiect.

    Context:
    - Materia: "{nume_materie}"
    - Secțiunea pe care o completăm: "{sectiune_fisa}"
    - Notițele brute scrise de profesor: "{notite_profesor}"

    Sarcina ta:
    Rescrie notițele brute într-un paragraf sau o listă la standarde universitare. 
    Dacă notițele sunt prea scurte, extinde-le logic bazându-te pe standardele moderne pentru materia respectivă.
    Oferă două variante de răspuns: una mai scurtă (un paragraf concis) și una mai detaliată (care poate conține și bullet points).

    Trebuie să răspunzi STRICT în format JSON:
    {{
        "varianta_1_scurta": "textul academic scurt generat aici...",
        "varianta_2_detaliata": "textul academic detaliat generat aici..."
    }}
    """
    
    max_reincercari = 3
    
    for incercare in range(max_reincercari):
        try:
            # Apelul către OpenAI
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7, # Creativitate academică
                response_format={"type": "json_object"} # Forțăm formatul JSON
            )
            
            # Extragem textul și îl parsăm ca JSON
            response_text = response.choices[0].message.content
            return json.loads(response_text)
            
        except Exception as exc:
            mesaj_eroare = str(exc).lower()
            # Dacă eroarea conține 429 (Too Many Requests) sau Rate Limit
            if "429" in mesaj_eroare or "rate limit" in mesaj_eroare or "quota" in mesaj_eroare:
                timp_asteptare = 10 # Așteptăm 10 secunde
                print(f"[⚠️ Avertisment] Limită de viteză atinsă la OpenAI. Aștept {timp_asteptare} secunde... (Încercarea {incercare + 1}/{max_reincercari})")
                time.sleep(timp_asteptare)
            else:
                # Dacă e o eroare generală (ex: fără internet sau JSON invalid)
                print(f"[ERROR] OpenAI API call failed: {exc}")
                return None
                
    print("[ERROR] Nu am reușit să generez textul nici după 3 încercări.")
    return None

if __name__ == "__main__":
    print("=== 🚀 Testare AI Copilot (OpenAI) ===")
    
    # Testăm scenariul
    rezultat = genereaza_text_copilot(
        nume_materie="Programare Web",
        sectiune_fisa="Tematica Cursului",
        notite_profesor="facem html, css, js si la final un proiect in react. examen grila si un proiect"
    )
    
    if rezultat:
        print("\n[✓] Text generat cu succes:")
        print(json.dumps(rezultat, indent=2, ensure_ascii=False))