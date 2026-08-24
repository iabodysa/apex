# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _

from apex.apex_core.setup.workflow_names import WORKFLOWS
from apex.apex_core.utils.app_owned_permissions import frappe_is_writing_its_own_records

WORKFLOW_CHILD_DOCTYPES = frozenset({"Workflow Document State", "Workflow Transition"})


def _shipped_workflow_name(doc) -> str | None:
    if doc.doctype in WORKFLOW_CHILD_DOCTYPES:
        candidate = doc.get("parent")
    else:
        candidate = doc.name
    return candidate if candidate in WORKFLOWS else None


def refuse_shipped_workflow_edit(doc, method=None, *args, **kwargs):
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
