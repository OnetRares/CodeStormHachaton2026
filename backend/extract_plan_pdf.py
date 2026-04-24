import pdfplumber
import json
import re
import argparse
from typing import List, Dict, Optional


def _normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip()
    # basic Romanian diacritics removal
    s = s.replace('ă', 'a').replace('â', 'a').replace('î', 'i')
    s = s.replace('ș', 's').replace('ş', 's').replace('ț', 't').replace('ţ', 't')
    return s.lower()


def _find_table_with_headers(tables: List[List[List[str]]]) -> Optional[Dict[str,int]]:
    # look for a table whose header row contains the expected columns
    required = {
        'discipline': ['discipline', 'disciplina', 'disciplinele', 'disciplină', 'disciplines'],
        'nr_ore': ['nr. de ore', 'nr ore', 'nr. ore', 'ore', 'nr_de_ore'],
        'forma': ['forma de verificare', 'forma verificare', 'verificare', 'forma'],
        'credite': ['credite', 'credit']
    }

    for table in tables:
        if not table or not table[0]:
            continue
        header = [ _normalize(cell) for cell in table[0] ]
        mapping = {}
        for i, cell in enumerate(header):
            for key, variants in required.items():
                for v in variants:
                    if v in cell:
                        mapping[key] = i
                        break
                if key in mapping:
                    break
        if set(required.keys()).issubset(set(mapping.keys())):
            return mapping
    return None


def _extract_number_from_cell(cell: str, prefer_label: Optional[str] = None) -> Optional[int]:
    if not cell:
        return None
    text = cell.replace('\n', ' ').lower()
    # try to find labeled numbers like 'curs 28' or 'curs:28'
    if prefer_label:
        m = re.search(rf"{prefer_label}\W*(\d+)", text)
        if m:
            return int(m.group(1))
    # fallback: find all integers and pick first
    nums = re.findall(r"(\d+)", text)
    if nums:
        return int(nums[0])
    return None


def _extract_code_from_name(name: str) -> (str, str):
    # Try to separate a leading code from the discipline name, e.g. "CS101 - Algorithms"
    if not name:
        return "", ""
    name = name.strip()
    m = re.match(r"^([A-Z0-9\-_.]{2,})\s*[-:]\s*(.+)$", name)
    if m:
        return m.group(1), m.group(2).strip()
    return "", name


def parse_plan_pdf(path: str) -> List[Dict]:
    results = []
    with pdfplumber.open(path) as pdf:
        # gather all tables from all pages
        collected_tables = []
        for page in pdf.pages:
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for t in tables:
                # normalize cells to str
                cleaned = [[(cell if cell is not None else '').strip() for cell in row] for row in t]
                collected_tables.append(cleaned)

        mapping = _find_table_with_headers(collected_tables)
        if mapping is None:
            raise ValueError("Could not find table with required headers: 'Discipline', 'Nr. de ore', 'Forma de verificare', 'Credite'.")

        # find the actual table again to iterate rows
        target_table = None
        for table in collected_tables:
            header = [ _normalize(cell) for cell in table[0] ]
            if set(mapping.keys()).issubset({k for k,v in mapping.items()}):
                # we already have mapping for header indexes; pick the first table matching that header pattern
                target_table = table
                break

        if target_table is None:
            raise RuntimeError("Target table not found after header mapping.")

        for row in target_table[1:]:
            # skip empty or separator rows
            if all(((c is None) or (str(c).strip() == '')) for c in row):
                continue
            # extract fields
            # cod_disciplina: try to extract from a dedicated column if exists; else attempt from name
            nume_cell = row[mapping['discipline']] if mapping['discipline'] < len(row) else ''
            cod, nume = _extract_code_from_name(nume_cell)

            nr_ore_cell = row[mapping['nr_ore']] if mapping['nr_ore'] < len(row) else ''
            ore_curs = _extract_number_from_cell(nr_ore_cell, prefer_label='curs')
            if ore_curs is None:
                ore_curs = _extract_number_from_cell(nr_ore_cell)
            ore_curs = int(ore_curs) if ore_curs is not None else 0

            forma_cell = row[mapping['forma']] if mapping['forma'] < len(row) else ''
            forma = (forma_cell.strip()[:1] if forma_cell and len(forma_cell.strip())>0 else '')

            credite_cell = row[mapping['credite']] if mapping['credite'] < len(row) else ''
            cred = _extract_number_from_cell(credite_cell)
            cred = int(cred) if cred is not None else 0

            obj = {
                'cod_disciplina': cod,
                'nume_disciplina': nume,
                'ore_curs': ore_curs,
                'forma_verificare': forma,
                'credite': cred
            }
            results.append(obj)

    return results


def main():
    parser = argparse.ArgumentParser(description='Extract Plan_Invatamant from a tabular PDF using pdfplumber')
    parser.add_argument('pdf', help='Path to PDF file')
    parser.add_argument('-o', '--output', help='Output JSON file (defaults to stdout)')
    args = parser.parse_args()

    data = parse_plan_pdf(args.pdf)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'Wrote {len(data)} items to {args.output}')
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
