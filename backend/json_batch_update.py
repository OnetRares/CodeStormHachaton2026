#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Dict, List

def batch_update_json_files(directory: Path, old_text: str, new_text: str) -> Dict[str, any]:
    """
    Scans a directory for .json files and replaces text in 'full_text' and 'pages'.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files_updated = 0
    total_matches = 0
    updated_file_names = []

    # Find all .json files in the directory
    json_files = list(directory.glob("*.json"))

    for json_path in json_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            content_changed = False
            
            # 1. Update full_text
            if "full_text" in data and old_text in data["full_text"]:
                count = data["full_text"].count(old_text)
                data["full_text"] = data["full_text"].replace(old_text, new_text)
                total_matches += count
                content_changed = True

            # 2. Update pages
            if "pages" in data:
                for page in data["pages"]:
                    if "text" in page and old_text in page["text"]:
                        count = page["text"].count(old_text)
                        page["text"] = page["text"].replace(old_text, new_text)
                        total_matches += count
                        content_changed = True

            if content_changed:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                files_updated += 1
                updated_file_names.append(json_path.name)

        except Exception as e:
            print(f"Error processing {json_path.name}: {e}")

    return {
        "files_updated": files_updated,
        "total_matches": total_matches,
        "updated_files": updated_file_names
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch update text in JSON files.")
    parser.add_argument("--dir", default="backend/output_json", help="Directory containing JSON files")
    parser.add_argument("--old", required=True, help="Text to search for")
    parser.add_argument("--new", required=True, help="Text to replace with")
    
    args = parser.parse_args()
    results = batch_update_json_files(Path(args.dir), args.old, args.new)
    print(json.dumps(results, indent=2))
