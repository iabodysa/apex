# Copyright (c) 2026, AFMCO and contributors
"""Party identity helpers for the arrival redesign (``party_type``/``party`` Dynamic Link).

The housed-worker doctypes — Accommodation Assignment / Checkout, Room Bed Transfer,
Accommodation Resident Request, Idle Resident Report, Accommodation Ledger and the
Masar Worker Token — carry the native ``party_type`` (Employee | Temporary Worker) +
``party`` Dynamic Link, mirroring the existing ``item_type``/``item`` precedent on
Accommodation Stock Ledger.

``employee`` is kept on each of these doctypes as a read-only compatibility mirror of
an Employee party, so existing reports and the daily cost engine — which skips rows
with no ``employee`` — keep working unchanged. A Temporary Worker party leaves
``employee`` empty (so the cost engine auto-skips the row) until a later batch links
the issued Iqama to a real Employee and back-dates the cost.
"""

from __future__ import annotations

import frappe
from frappe import _

PARTY_EMPLOYEE = "Employee"
PARTY_TEMPORARY_WORKER = "Temporary Worker"
# [#qnlgbm]
PARTY_TYPE_OPTIONS = f"{PARTY_EMPLOYEE}\n{PARTY_TEMPORARY_WORKER}"


def sync_party_employee(
    doc,
    derive_from: str | None = None,
    require_party: bool = False,
    employee_field: str = "employee",
) -> None:
    """Keep ``party_type``/``party`` and a legacy Employee link in step.

    Call once, early — from the doctype's ``before_validate`` (or its existing
    ``validate`` / ``before_save`` handler), before any logic that reads the Employee
    link.

    :param derive_from: name of a Link field on ``doc`` whose target itself carries
        ``party_type``/``party`` (e.g. ``"assignment"``). When set and ``doc`` has no
        party of its own, the party is inherited from that parent — used by
        Accommodation Checkout and Room Bed Transfer.
    :param require_party: when True, raise if neither ``party`` nor the Employee link
        is present (replaces the old field-level ``reqd`` on user-entered docs).
    :param employee_field: the legacy Employee Link fieldname to mirror. Defaults to
        ``"employee"``; the custody doctypes use ``"issued_to_employee"`` /
        ``"returned_by_employee"``.
    """
    # [#jolp3a]
    if derive_from and not doc.get("party"):
        parent = doc.get(derive_from)
        if parent:
            parent_doctype = doc.meta.get_field(derive_from).options
            row = frappe.db.get_value(parent_doctype, parent, ["party_type", "party"])
            if row and row[0]:
                doc.party_type, doc.party = row[0], row[1]

    # [#dq7is9]
    if not doc.get("party_type") and doc.get(employee_field):
        doc.party_type = PARTY_EMPLOYEE

    # [#70ucun]
    if doc.get("party_type") == PARTY_EMPLOYEE:
        if doc.get("party"):
            setattr(doc, employee_field, doc.party)
        elif doc.get(employee_field):
            doc.party = doc.get(employee_field)
    elif doc.get("party_type") == PARTY_TEMPORARY_WORKER:
        # [#2jpjl3]
        setattr(doc, employee_field, None)

    # [#pr7aug]
    if require_party and not doc.get("party") and not doc.get(employee_field):
        # [#1p2u7t]
        frappe.throw(_("Resident / worker is required."), frappe.MandatoryError)
