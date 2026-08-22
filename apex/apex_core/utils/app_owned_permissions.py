# Copyright (c) 2026, afmcoltd
"""Refuse a permission edit that the next update would silently undo.

Three DocTypes carry their permissions in this app's customization files —
``apex/habitat/custom/employee.json``, ``cost_center.json`` and ``project.json``, each
with ``sync_on_migrate`` set. Frappe's customization sync does not merge those rows: at
``frappe/modules/utils.py:184-186`` it deletes every Custom DocPerm for the DocType and
reinserts only the file's, and its own comment says so — "Docperm have no sync as of
now. They get OVERRIDDEN on sync."

So a grant made in Role Permission Manager is accepted, saved, and gone at the next
``bench migrate``, with nothing said. Refusing the write is the honest version of the
same outcome: the administrator learns immediately instead of discovering it when a role
he granted stops working.

The sync's own reinserts must pass, which is why the refusal stands down while Frappe is
installing, migrating or running a patch.
"""

from __future__ import annotations

import frappe
from frappe import _

APP_OWNED_DOCTYPES = frozenset({"Employee", "Cost Center", "Project"})


def _frappe_is_writing_its_own_records() -> bool:
    """True while Frappe is applying shipped records rather than serving a person.

    A refusal that cannot tell the two apart fails the customer's own upgrade. ``validate``
    still runs during a fixture import — ``import_file.py:233`` sets ``ignore_validate``
    only when ``data_import`` is false, and fixtures pass it true — so ``in_import`` has to
    be in this test, not only the three that a migrate or an install would set.
    """
    return bool(
        frappe.flags.in_migrate
        or frappe.flags.in_install
        or frappe.flags.in_patch
        or frappe.flags.in_import
    )


def refuse_app_owned_permission_edit(doc, method=None):
    """Refuse a hand-made Custom DocPerm on a DocType whose permissions ship with Apex."""
    if doc.parent not in APP_OWNED_DOCTYPES:
        return
    if _frappe_is_writing_its_own_records():
        return
    frappe.throw(
        _(
            "Permissions for {0} are set by Apex and reapplied on every update, so a"
            " change made here would be removed the next time the site is updated. Ask"
            " for the change to ship with the app instead."
        ).format(_(doc.parent)),
        frappe.PermissionError,
        title=_("Set by Apex"),
    )
