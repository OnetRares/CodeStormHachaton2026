#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SENTENCE_SPLIT_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)", flags=re.UNICODE)


def _extract_changed_sentences(
    text: str,
    old_text: str,
    new_text: str,
) -> list[dict[str, Any]]:
    if not text or old_text not in text:
        return []

    examples: list[dict[str, Any]] = []
    for match in SENTENCE_SPLIT_RE.finditer(text):
        sentence = " ".join(match.group(0).split()).strip()
        if not sentence or old_text not in sentence:
            continue

        replaced_sentence = sentence.replace(old_text, new_text)
        examples.append(
            {
                "before": sentence,
                "after": replaced_sentence,
                "occurrences": sentence.count(old_text),
            }
        )
    return examples


def _resolve_target_files(directory: Path, target_file: str | None) -> list[Path]:
    if target_file and target_file.strip():
        target_name = Path(target_file.strip()).name
        direct_path = directory / target_name
        if not direct_path.exists():
            raise FileNotFoundError(f"Target JSON file not found: {target_name}")
        return [direct_path]
    return sorted(directory.glob("*.json"))


def batch_update_json_files(
    directory: Path,
    old_text: str,
    new_text: str,
    target_file: str | None = None,
) -> dict[str, Any]:
    """
    Scans a directory for .json files and replaces text in 'full_text' and 'pages'.
    Also returns sentence-level examples before/after replacement.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not old_text:
        raise ValueError("old_text must not be empty")

    json_files = _resolve_target_files(directory, target_file)
    files_updated = 0
    total_matches = 0
    updated_file_names: list[str] = []
    file_details: list[dict[str, Any]] = []
    sentence_examples: list[dict[str, Any]] = []

    for json_path in json_files:
        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            file_matches = 0
            file_examples: list[dict[str, Any]] = []
            pages = data.get("pages")
            has_pages = isinstance(pages, list) and len(pages) > 0

            if has_pages:
                for page in pages:
                    page_text = page.get("text", "")
                    if not isinstance(page_text, str) or old_text not in page_text:
                        continue

                    match_count = page_text.count(old_text)
                    file_matches += match_count

                    page_examples = _extract_changed_sentences(
                        text=page_text,
                        old_text=old_text,
                        new_text=new_text,
                    )

                    page_number = page.get("page")
                    for example in page_examples:
                        file_examples.append(
                            {
                                "file": json_path.name,
                                "page": page_number,
                                **example,
                            }
                        )

                    page["text"] = page_text.replace(old_text, new_text)

                if isinstance(data.get("full_text"), str):
                    data["full_text"] = data["full_text"].replace(old_text, new_text)
            else:
                full_text = data.get("full_text", "")
                if isinstance(full_text, str) and old_text in full_text:
                    file_matches = full_text.count(old_text)
                    file_examples = [
                        {
                            "file": json_path.name,
                            "page": None,
                            **example,
                        }
                        for example in _extract_changed_sentences(
                            text=full_text,
                            old_text=old_text,
                            new_text=new_text,
                        )
                    ]
                    data["full_text"] = full_text.replace(old_text, new_text)

            if file_matches > 0:
                with open(json_path, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)

                files_updated += 1
                total_matches += file_matches
                updated_file_names.append(json_path.name)
                file_details.append(
                    {
                        "file": json_path.name,
                        "matches": file_matches,
                        "sentence_examples": file_examples,
                    }
                )

                sentence_examples.extend(file_examples)
        except Exception as exc:
            print(f"Error processing {json_path.name}: {exc}")

    return {
        "files_updated": files_updated,
        "total_matches": total_matches,
        "updated_files": updated_file_names,
        "file_details": file_details,
        "sentence_examples": sentence_examples,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Batch update text in JSON files.")
    parser.add_argument("--dir", default="backend/output_json", help="Directory containing JSON files")
    parser.add_argument("--old", required=True, help="Text to search for")
    parser.add_argument("--new", required=True, help="Text to replace with")
    parser.add_argument("--target-file", default=None, help="Optional single JSON file name to update")

    args = parser.parse_args()
    results = batch_update_json_files(
        directory=Path(args.dir),
        old_text=args.old,
        new_text=args.new,
        target_file=args.target_file,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
