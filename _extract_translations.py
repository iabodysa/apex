"""
Temporary script: Extract all translatable strings from DocType JSON files.
Outputs a Frappe-compatible ar.csv translation file.
"""

import json
import os
import csv
import glob

DOCTYPE_DIR = os.path.join(
    os.path.dirname(__file__),
    "apex_habitat", "habitat", "doctype"
)
OUTPUT_CSV = os.path.join(
    os.path.dirname(__file__),
    "apex_habitat", "apex_habitat", "translations", "ar.csv"
)

# Collect unique strings
strings = set()

def add(text):
    """Add a non-empty, non-trivial string."""
    if not text or not isinstance(text, str):
        return
    text = text.strip()
    if not text or text.isdigit():
        return
    # Skip technical/internal values
    skip_values = {
        "DocType", "DocField", "DocPerm", "InnoDB",
        "DESC", "ASC", "modified", "creation",
        "0", "1", "field:", "hash", "autoincrement",
    }
    if text in skip_values:
        return
    strings.add(text)


def extract_from_doctype(json_path):
    """Extract all translatable strings from a single DocType JSON."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    # DocType name
    add(data.get("name"))

    # DocType description
    add(data.get("description"))

    # Fields
    for field in data.get("fields", []):
        # Field label
        add(field.get("label"))

        # Field description / placeholder
        add(field.get("description"))
        add(field.get("placeholder"))

        # Select options (split by newline)
        options = field.get("options", "")
        if field.get("fieldtype") == "Select" and options:
            for opt in options.split("\n"):
                opt = opt.strip()
                if opt:
                    add(opt)

        # Section Break / Column Break labels
        if field.get("fieldtype") in ("Section Break", "Column Break", "Tab Break"):
            add(field.get("label"))

    # Permissions - Role names
    for perm in data.get("permissions", []):
        add(perm.get("role"))

    # Workspace labels (if present)
    for link in data.get("links", []):
        add(link.get("label"))
        add(link.get("description"))

    # Actions
    for action in data.get("actions", []):
        add(action.get("label"))

    # States
    for state in data.get("states", []):
        add(state.get("title"))


def extract_from_python_files():
    """Extract _() translation calls from Python files."""
    py_dir = os.path.join(os.path.dirname(__file__), "apex_habitat", "habitat")
    import re
    pattern = re.compile(r'_\(\s*["\'](.+?)["\']\s*\)')

    for root, dirs, files in os.walk(py_dir):
        # Skip __pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                for match in pattern.findall(content):
                    add(match)
            except IOError:
                pass


def extract_from_workspace_json():
    """Extract labels from workspace JSON files."""
    ws_dir = os.path.join(
        os.path.dirname(__file__),
        "apex_habitat", "apex_habitat", "workspace"
    )
    if not os.path.isdir(ws_dir):
        return
    for json_path in glob.glob(os.path.join(ws_dir, "*.json")):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        add(data.get("label"))
        add(data.get("title"))

        for link in data.get("links", []):
            add(link.get("label"))
            add(link.get("description"))

        for shortcut in data.get("shortcuts", []):
            add(shortcut.get("label"))

        for card in data.get("cards", []):
            add(card.get("label"))
            for link in card.get("links", []):
                add(link.get("label"))
                add(link.get("description"))


def main():
    # 1. Extract from all DocType JSON files
    for root, dirs, files in os.walk(DOCTYPE_DIR):
        for fname in files:
            if fname.endswith(".json"):
                extract_from_doctype(os.path.join(root, fname))

    # 2. Extract from Python _() calls
    extract_from_python_files()

    # 3. Extract from Workspace JSON
    extract_from_workspace_json()

    # 4. Sort and write CSV
    sorted_strings = sorted(strings, key=lambda s: s.lower())

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for s in sorted_strings:
            # Frappe format: source_string,translated_string,context(optional)
            writer.writerow([s, "", ""])

    print(f"Done! Extracted {len(sorted_strings)} unique translatable strings.")
    print(f"Output: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
