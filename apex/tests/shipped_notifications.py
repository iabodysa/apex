# Copyright (c) 2026, AFMCO and contributors
"""Read the app's shipped is_standard Notification JSON straight off disk.

The sibling of ``shipped_doctypes.py``, and it exists for the same reason: a
second guard needed the same parse and the copy-paste detector would have caught
the duplicate. ``test_release_hygiene`` already carried two private scanners over
this directory tree (one harvesting recipient roles, one listing companion dirs);
both now read from here, so the three consumers cannot drift apart on what
"a shipped notification" means.

Deliberately NOT named ``test_*``: ``tests/test_no_cross_test_imports.py`` bans a
test module importing a sibling test module, and ``apex_core/utils/
test_notification_role_guard.py`` is colocated with the guard it proves. A plain
name is the sanctioned shape for shared test logic (the same reason
``factories.py``, ``shipped_doctypes.py`` and ``workspace_reachability.py``
carry plain names), and it keeps the colocation ratchet — which counts
``test_*.py`` under ``tests/`` — unmoved.
"""

import glob
import json
import os

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# One level of module dir, then `notification/<slug>/<slug>.json`. NOT recursive:
# the recursive form also swept `node_modules`, which is why the older scanner
# carried an explicit exclusion for it.
NOTIFICATION_GLOB = os.path.join(APP_ROOT, "*", "notification", "*", "*.json")


def shipped_notifications():
    """``[(abs_path, data)]`` for every is_standard Notification the app ships.

    Sorted by path so a baseline built from this is stable across machines. Both
    filters are load-bearing: a notification directory can hold JSON that is not
    the Notification record, and a non-``is_standard`` row is site data that this
    app does not own. An unparseable or unreadable file is skipped rather than
    raised on — a guard reports what ships, it does not die on one bad neighbour.
    """
    out = []
    for path in sorted(glob.glob(NOTIFICATION_GLOB)):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("doctype") != "Notification":
            continue
        if not data.get("is_standard"):
            continue
        out.append((path, data))
    return out


def notification_role_pairs():
    """``[(notification_name, document_type, role, enabled)]`` — one per receiver.

    A notification with two ``receiver_by_role`` rows yields two pairs, because
    the permission question is asked once per role. Recipients that name no role
    (``receiver_by_document_field``, ``send_to_all_assignees``) are not pairs:
    they resolve to a person, not to an audience this app declares.
    """
    pairs = []
    for _path, data in shipped_notifications():
        for recipient in data.get("recipients") or []:
            role = recipient.get("receiver_by_role")
            if not role:
                continue
            pairs.append(
                (
                    data.get("name"),
                    data.get("document_type"),
                    role,
                    bool(data.get("enabled")),
                )
            )
    return pairs
