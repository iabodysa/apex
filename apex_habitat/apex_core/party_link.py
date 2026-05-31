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
# Select options string shared by every ``party_type`` field. Keep in step with the
# DocType JSON ``party_type.options``.
PARTY_TYPE_OPTIONS = f"{PARTY_EMPLOYEE}\n{PARTY_TEMPORARY_WORKER}"


def sync_party_employee(doc, derive_from: str | None = None, require_party: bool = False) -> None:
    """Keep ``party_type``/``party`` and the legacy ``employee`` link in step.

    Call once, early — from the doctype's ``before_validate`` (or its existing
    ``validate`` / ``before_save`` handler), before any logic that reads ``employee``.

    :param derive_from: name of a Link field on ``doc`` whose target itself carries
        ``party_type``/``party`` (e.g. ``"assignment"``). When set and ``doc`` has no
        party of its own, the party is inherited from that parent — used by
        Accommodation Checkout and Room Bed Transfer.
    :param require_party: when True, raise if neither ``party`` nor ``employee`` is
        present (replaces the old ``employee`` mandatory flag on user-entered docs).
    """
    # 1) Inherit identity from a parent record (e.g. Accommodation Assignment).
    if derive_from and not doc.get("party"):
        parent = doc.get(derive_from)
        if parent:
            parent_doctype = doc.meta.get_field(derive_from).options
            row = frappe.db.get_value(parent_doctype, parent, ["party_type", "party"])
            if row and row[0]:
                doc.party_type, doc.party = row[0], row[1]

    # 2) Normalise an absent party_type to Employee when a legacy employee is set, so
    #    code paths that build a doc dict directly (e.g. the daily cost engine) — which
    #    do not get the field default applied — still produce a matching party.
    if not doc.get("party_type") and doc.get("employee"):
        doc.party_type = PARTY_EMPLOYEE

    # [AHX-INV-0004] Mirror between party and the legacy employee link.
    if doc.get("party_type") == PARTY_EMPLOYEE:
        if doc.get("party"):
            doc.employee = doc.party
        elif doc.get("employee"):
            doc.party = doc.employee
    elif doc.get("party_type") == PARTY_TEMPORARY_WORKER:
        # No Employee yet — leave `employee` empty so the cost engine skips the row.
        doc.employee = None

    # 4) Optional integrity guard (replaces the legacy `employee` reqd).
    if require_party and not doc.get("party") and not doc.get("employee"):
        # MandatoryError (a ValidationError subclass): the party/employee identity
        # replaces the old field-level `employee` reqd, so this stays the same
        # exception class callers and tests already expect for a missing identity.
        frappe.throw(_("Resident / worker is required."), frappe.MandatoryError)
