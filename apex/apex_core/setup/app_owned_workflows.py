# Copyright (c) 2026, afmcoltd
"""Refuse a workflow edit the next update would silently undo.

Apex ships sixteen Workflow definitions through ``fixtures`` in ``hooks.py``. A fixture
is reimported with ``force=True`` (``data_import.py:288``), and ``import_file.py:130``
puts the hash/timestamp skip gate behind ``if not force`` — so the file is applied on
EVERY migrate whether or not anything changed.

For a Workflow that means the whole definition is rewritten: the states, their allowed
roles, the transitions and ``is_active``. A supervisor who adds a transition, widens a
role or switches a workflow off in the UI keeps that change until the next update and
then loses it, with nothing said and nothing to search for.

Refusing the write is the honest version of the same outcome. The administrator learns
at the moment of the edit rather than discovering weeks later that an approval step he
removed is back. Only the SIXTEEN names Apex ships are covered; a workflow the operator
creates is not in the file, is never reimported, and is untouched here.

The child rows are covered too, because editing a transition never touches the parent
document's own name: ``Workflow Document State`` and ``Workflow Transition`` carry the
workflow in ``parent``, so the refusal reads that instead.

``Salis Settings.enable_approvals`` remains the supported way to turn approvals off. It
reaches ``is_active`` through ``apply_approval_switch``, which writes with
``frappe.db.set_value`` — that path runs no ``validate``, so this refusal never sees it
and could not block it. If that write is ever changed to a document save, this refusal
will start refusing the app's own switch, and the stand-down below is what would have to
grow to cover it.
"""

from __future__ import annotations

import frappe
from frappe import _

from apex.apex_core.setup.workflow_names import WORKFLOWS
from apex.apex_core.utils.app_owned_permissions import frappe_is_writing_its_own_records

WORKFLOW_CHILD_DOCTYPES = frozenset({"Workflow Document State", "Workflow Transition"})


def _shipped_workflow_name(doc) -> str | None:
    """The shipped Workflow this document belongs to, or None.

    A child row names its workflow in ``parent``; the Workflow itself names it in
    ``name``. Returning None for anything else is what keeps an operator's own
    workflow out of the refusal.
    """
    if doc.doctype in WORKFLOW_CHILD_DOCTYPES:
        candidate = doc.get("parent")
    else:
        candidate = doc.name
    return candidate if candidate in WORKFLOWS else None


def refuse_shipped_workflow_edit(doc, method=None, *args, **kwargs):
    """Refuse editing, renaming or deleting a Workflow the app ships.

    Stands down while Frappe is installing, migrating, patching or importing, so the
    fixture's own reimport still lands — see
    :func:`apex_core.utils.app_owned_permissions.frappe_is_writing_its_own_records`.
    """
    shipped = _shipped_workflow_name(doc)
    if not shipped:
        return
    if frappe_is_writing_its_own_records():
        return
    frappe.throw(
        _(
            "{0} is a workflow Apex ships, and every update rewrites it as the app"
            " defines it. A change made here would be removed the next time the site is"
            " updated. Ask for the change to ship with the app."
        ).format(_(shipped)),
        frappe.PermissionError,
        title=_("Set by Apex"),
    )
