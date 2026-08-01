#!/usr/bin/env python3
# Copyright (c) 2026, AFMCO and contributors
"""Generate docs/reference/permissions.md from the DocPerm rows apex ships.

The published permission matrices were hand-maintained and had rotted: DocTypes
listed under names the app no longer shipped, and rights columns that named a
role the JSON grants nothing. Deriving the page from the same JSON the site
installs removes the class of defect instead of detecting it, so the only check
the page still needs is that regenerating it changes nothing.

Deterministic by construction: every collection is sorted, no timestamp, no
commit id, no host path. Same tree in, byte-identical file out.

    python3 scripts/build_permissions_reference.py           # write the page
    python3 scripts/build_permissions_reference.py --check   # exit 1 if stale
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(REPO_ROOT, "apex")
OUTPUT = os.path.join(REPO_ROOT, "docs", "reference", "permissions.md")
GENERATOR = "scripts/build_permissions_reference.py"

# The rights a Frappe DocPerm row can carry, split the way an operator reads them:
# what the role may do to a document, and what it may do with the data.
DOCUMENT_RIGHTS = ("read", "write", "create", "submit", "cancel", "amend", "delete")
DATA_RIGHTS = ("report", "export", "print", "email", "share", "select", "import")
ADMIN_RIGHTS = ("set_user_permissions",)

LABELS = {
    "read": "Read",
    "write": "Write",
    "create": "Create",
    "submit": "Submit",
    "cancel": "Cancel",
    "amend": "Amend",
    "delete": "Delete",
    "report": "Report",
    "export": "Export",
    "print": "Print",
    "email": "Email",
    "share": "Share",
    "select": "Select",
    "import": "Import",
    "set_user_permissions": "Set user permissions",
}

NONE = "—"

PREAMBLE = """# Permissions reference

<!-- Generated from the shipped DocType JSON. Do not edit by hand.
     Rebuild:  python3 {generator} -->

Every DocPerm row apex ships, one row per grant. This page is derived from the
same JSON a site installs, so it cannot disagree with the running permissions.

## DocPerm is not effective access

A DocPerm row is the widest a role can act; three other layers narrow it.

- A **Frappe Workflow** decides which transitions a role may make on a document
  that is otherwise writable.
- **Row scope** decides which records come back. Fleet Project Manager and Fleet
  Supervisor are scoped by User Permission on Project; Resident Supervisor is
  scoped by User Permission on Building. `apex/habitat/permissions.py` and the
  Salis scope modules own that side.
- **Permlevel** splits a document into field bands. A permlevel-1 row grants
  nothing on the ordinary fields; it opens the fields tagged at that level.

Workspace, desk page and portal navigation grant no data rights at all. A role
that reaches a screen still resolves every record through the rows below.

Who each role is written for is a judgement rather than a schema fact, so the
role charters stay in [the training index](../training/README.md).

## Two grants are not in this table

Both are Custom DocPerm rows written at install and migrate time against core
DocTypes apex does not own, so no shipped JSON carries them:

- `apex/apex_core/setup/seeders/habitat_core_link_perms_seed.py` grants Habitat
  roles `select` on Employee, Project and Cost Center so their own Link fields
  and register reports resolve.
- `apex/apex_core/setup/seeders/salis_issue_seed.py` does the same for Issue.

## Reading a row

**Document rights** and **Data rights** list only what the row actually grants;
`{none}` means none of that group. **Level** is the permlevel — `0` is the
document itself, a higher number is a field band. **Row filter** reads
`Own records only` when the row carries `if_owner`.

DocTypes that ship no DocPerm row of their own are listed under each module. A
child table takes its access from the parent document it sits in.
"""


def _doctype_files(app_root: str) -> list[str]:
    """Every `<slug>/<slug>.json` under a `doctype/` directory, sorted by path."""
    found = []
    for directory, _subdirs, filenames in os.walk(app_root):
        if os.path.basename(os.path.dirname(directory)) != "doctype":
            continue
        slug = os.path.basename(directory)
        candidate = os.path.join(directory, slug + ".json")
        if os.path.isfile(candidate):
            found.append(candidate)
    return sorted(found)


def shipped_doctypes(app_root: str = APP_ROOT) -> list[dict]:
    """Every DocType apex ships, as {name, module, istable, submittable, rows}."""
    records = []
    for path in _doctype_files(app_root):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("doctype") != "DocType":
            continue
        records.append(
            {
                "name": data.get("name") or "",
                "module": data.get("module") or "Unassigned",
                "istable": bool(data.get("istable")),
                "submittable": bool(data.get("is_submittable")),
                "rows": list(data.get("permissions") or []),
            }
        )
    return sorted(records, key=lambda record: (record["module"], record["name"]))


def _rights(row: dict, group: tuple) -> str:
    granted = [LABELS[flag] for flag in group if row.get(flag)]
    return ", ".join(granted) if granted else NONE


def _annotate(record: dict) -> str:
    if record["istable"]:
        return f"{record['name']} (child table)"
    if record["submittable"]:
        return f"{record['name']} (submittable)"
    return record["name"]


def _sorted_rows(record: dict) -> list[dict]:
    return sorted(
        record["rows"],
        key=lambda row: (int(row.get("permlevel") or 0), str(row.get("role") or "")),
    )


def _anchor(module: str) -> str:
    return module.lower().replace(" ", "-")


def _module_section(module: str, records: list[dict]) -> list[str]:
    lines = [f"## {module}", ""]
    granting = [record for record in records if record["rows"]]
    silent = [record for record in records if not record["rows"]]

    if granting:
        lines += [
            "| DocType | Role | Level | Document rights | Data rights | Row filter |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for record in granting:
            label = _annotate(record)
            for row in _sorted_rows(record):
                admin = _rights(row, ADMIN_RIGHTS)
                data = _rights(row, DATA_RIGHTS)
                if admin != NONE:
                    data = admin if data == NONE else f"{data}, {admin}"
                lines.append(
                    "| {doctype} | {role} | {level} | {document} | {data} | {filter} |".format(
                        doctype=label,
                        role=row.get("role") or "",
                        level=int(row.get("permlevel") or 0),
                        document=_rights(row, DOCUMENT_RIGHTS),
                        data=data,
                        filter="Own records only" if row.get("if_owner") else NONE,
                    )
                )
        lines.append("")

    if silent:
        names = ", ".join(_annotate(record) for record in silent)
        lines += [f"No DocPerm row of its own: {names}.", ""]
    return lines


def render(records: list[dict] | None = None) -> str:
    records = shipped_doctypes() if records is None else records
    modules: dict[str, list[dict]] = {}
    for record in records:
        modules.setdefault(record["module"], []).append(record)

    granting = [record for record in records if record["rows"]]
    rows = sum(len(record["rows"]) for record in records)
    roles = {str(row.get("role") or "") for record in records for row in record["rows"]}

    lines = [PREAMBLE.format(generator=GENERATOR, none=NONE).rstrip(), ""]
    lines += [
        "## Coverage",
        "",
        "| Measure | Count |",
        "| --- | --- |",
        f"| DocTypes shipped | {len(records)} |",
        f"| DocTypes granting at least one role | {len(granting)} |",
        f"| DocPerm rows | {rows} |",
        f"| Roles granted | {len(roles)} |",
        "",
        "## Roles",
        "",
        "| Role | DocTypes | DocPerm rows |",
        "| --- | --- | --- |",
    ]
    for role in sorted(roles):
        held = [record for record in records if any(r.get("role") == role for r in record["rows"])]
        count = sum(1 for record in records for r in record["rows"] if r.get("role") == role)
        lines.append(f"| {role} | {len(held)} | {count} |")
    lines.append("")

    lines += ["## Modules", ""]
    for module in sorted(modules):
        lines.append(f"- [{module}](#{_anchor(module)})")
    lines.append("")

    for module in sorted(modules):
        lines += _module_section(module, modules[module])

    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the file on disk differs from what this run would write",
    )
    parser.add_argument("--output", default=OUTPUT, help="destination path")
    args = parser.parse_args(argv)

    page = render()
    if args.check:
        current = ""
        if os.path.isfile(args.output):
            with open(args.output, encoding="utf-8") as handle:
                current = handle.read()
        if current == page:
            return 0
        sys.stderr.write(
            f"{os.path.relpath(args.output, REPO_ROOT)} is stale — run: python3 {GENERATOR}\n"
        )
        return 1

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
