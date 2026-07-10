# Copyright (c) 2026, AFMCO and contributors
"""Cutover stamp: pin every already-onboarded User's ``last_known_versions``
[apex] to the FINAL v1 changelog version, so the v2.0.0 "Updated To A New
Version" popup replay starts clean.

Mechanism (``frappe.utils.change_log.get_change_log``): the popup lists every
``change_log/v<major>/vX_Y_Z.md`` whose version is GREATER than
``User.last_known_versions["apex"]["version"]`` (default ``0.0.1``) and
LESS-OR-EQUAL to the running ``apex.__version__``. At the v2.0.0 cutover
``__version__`` becomes ``2.0.0``; a user still stamped at, say, ``1.55.0`` would
be replayed the whole ``1.56 → 2.0.0`` history on next login.

This pins each populated map to the final v1 series head (the highest
``change_log/v1/vX_Y_Z.md`` on disk — ``1.62.0`` today, derived, never
hardcoded). Result: at v2.0.0 the user sees ONLY the new ``change_log/v2/v2_0_0.md``
note, not the v1 back-catalogue.

Why the final v1 version and NOT ``__version__`` (2.0.0): stamping to 2.0.0 would
suppress the v2.0.0 popup itself. This supersedes
``v1_x.stamp_changelog_seen_version`` (which stamps to the live ``__version__`` and
would therefore stamp 2.0.0 at cutover — that entry is RETIRED from patches.txt in
the same B9 change so the two cannot race).

Only users with a NON-empty ``last_known_versions`` map are touched; a brand-new
user with an empty value is left for Frappe's native first-login seeding. Never
downgrades a user already at/above the final v1 version. Idempotent; no-op on a
re-run and on fresh installs (fresh installs never replay patches).
"""

import json
import os

import frappe


def _final_v1_version():
    """Highest ``change_log/v1/vX_Y_Z.md`` version, as an ``(x, y, z)`` tuple and
    its dotted string. Returns ``(None, None)`` when the folder is absent."""
    app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    v1_dir = os.path.join(app_dir, "change_log", "v1")
    if not os.path.isdir(v1_dir):
        return None, None
    best = None
    for fname in os.listdir(v1_dir):
        if not fname.endswith(".md"):
            continue
        stem = fname[:-3]
        parts = stem.split("_")
        # [#gdnkui]
        if len(parts) != 3 or not parts[0].startswith("v"):
            continue
        try:
            nums = (int(parts[0][1:]), int(parts[1]), int(parts[2]))
        except ValueError:
            continue
        if best is None or nums > best:
            best = nums
    if best is None:
        return None, None
    return best, "{}.{}.{}".format(*best)


def _parse(version):
    """'1.62.0' -> (1, 62, 0); unparseable -> None."""
    if not version or not isinstance(version, str):
        return None
    parts = version.split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return None


def execute():
    target_tuple, target_str = _final_v1_version()
    if not target_str:
        return  # [#svvo8f]

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
            # [#l73n99]
            continue

        entry = known.get("apex")
        current = _parse(entry.get("version")) if isinstance(entry, dict) else None
        # [#twaiyc]
        if current is not None and current >= target_tuple:
            continue

        if isinstance(entry, dict):
            entry["version"] = target_str
        else:
            known["apex"] = {"version": target_str}

        frappe.db.set_value(
            "User",
            row["name"],
            "last_known_versions",
            json.dumps(known),
            update_modified=False,
        )
