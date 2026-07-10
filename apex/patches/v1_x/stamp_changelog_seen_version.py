# Copyright (c) 2026, AFMCO and contributors
"""Stamp this app's seen version into each already-onboarded User's
``last_known_versions`` so Frappe's native What's New popup does not replay the
whole apex release history.

Frappe's popup (``frappe.utils.change_log.get_change_log``) compares the current
``apex.__version__`` against ``User.last_known_versions["apex"]
["version"]`` (defaulting to ``0.0.1`` when the key is missing). A user who has
already passed the popup once has a NON-empty ``last_known_versions`` but may have
no apex entry (or a stale one), so on the next login the popup dumps the
app's entire changelog from 0.0.1.

This sets the apex ``version`` to the current ``__version__`` for every
user that already has a populated ``last_known_versions`` (a brand-new user with an
empty value is intentionally left alone — Frappe seeds it on first login and shows
nothing). Every other app's entry is preserved untouched. Idempotent: a re-run
finds the version already current and writes nothing.
"""

import json

import frappe


def execute():
    try:
        current_version = frappe.get_attr("apex.__version__")
    except Exception:
        return

    rows = frappe.get_all(
        "User",
        filters={"last_known_versions": ["is", "set"]},
        fields=["name", "last_known_versions"],
    )
    for row in rows:
        raw = row.get("last_known_versions")
        if not raw:
            continue
        try:
            known = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(known, dict) or not known:
            # [#8gjssk]
            continue

        entry = known.get("apex")
        if isinstance(entry, dict) and entry.get("version") == current_version:
            continue  # [#bfpto6]

        if isinstance(entry, dict):
            entry["version"] = current_version
        else:
            known["apex"] = {"version": current_version}

        frappe.db.set_value(
            "User",
            row["name"],
            "last_known_versions",
            json.dumps(known),
            update_modified=False,
        )
