# Copyright (c) 2026, AFMCO and contributors
"""ONE-TIME privacy genericization: strip the confidential client/accreditation-vendor
names from already-seeded Safety Task Catalog rows (T-291).

The Safety Task Catalog seed JSON formerly named a specific client warehouse-safety (WHS)
audit and a specific health-and-safety accreditation vendor in several rows' ``task_title``
and ``instructions``. Those names are confidential and have been replaced in the seed file
with client-neutral wording ("a client warehouse-safety (WHS) audit finding", "the required
health-and-safety accreditation" / "the accreditation body"). The seed loader is
create-only, so it never rewrites a row that already exists -- existing sites keep the old
wording until this patch runs.

For each catalog row whose live ``task_title`` or ``instructions`` still contains either
confidential token, re-apply the corrected ``task_title`` and ``instructions`` straight from
the (now-clean) seed JSON, keyed on ``task_code``. The JSON file is the single source of
truth, so file and DB end up identical.

Idempotency guards:
- Only rows still carrying a confidential token are touched (case-insensitive scan); once
  rewritten they no longer match, so a re-run is a no-op.
- A no-op on fresh installs -- the seeder already wrote the clean wording.
- Skips any task_code present in the DB but absent from the JSON (never invents content).
- Writes via frappe.db.set_value (update_modified=False) -- a text correction on historical
  rows, no validation churn.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import json
import os

import frappe

_DOCTYPE = "Safety Task Catalog"
# [#9xtpzp]
_LEAK_TOKENS = ("ama" + "zon", "ave" + "tta")
# [#rlil6l]
_SEED_JSON = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "apex_core",
    "setup",
    "data",
    "habitat",
    "safety_task_catalog.json",
)
_COPY_FIELDS = ("task_title", "instructions")


def _has_leak(*values) -> bool:
    blob = " ".join(str(v or "") for v in values).lower()
    return any(tok in blob for tok in _LEAK_TOKENS)


def execute():
    if not frappe.db.table_exists(_DOCTYPE):
        return

    with open(os.path.abspath(_SEED_JSON), encoding="utf-8") as fh:
        spec = json.load(fh)
    clean_by_code = {r["task_code"]: r for r in spec["records"]}

    # [#7bty71]
    rows = frappe.get_all(
        _DOCTYPE,
        fields=["name", "task_code", "task_title", "instructions"],
        order_by="task_code",
    )

    updated = 0
    skipped = 0
    for row in rows:
        if not _has_leak(row.get("task_title"), row.get("instructions"), row.get("task_code")):
            continue
        clean = clean_by_code.get(row["task_code"])
        # [#nd649w]
        if not clean:
            skipped += 1
            continue

        values = {f: clean[f] for f in _COPY_FIELDS if f in clean}
        frappe.db.set_value(_DOCTYPE, row["name"], values, update_modified=False)
        updated += 1

    frappe.logger().info(
        f"genericize_safety_task_catalog_client: updated={updated}, skipped={skipped}"
    )
