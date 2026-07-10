# Copyright (c) 2026, AFMCO and contributors
"""Exception Workbench backend for the Logistay module.

The read + act surface over the immutable Timesheet Exception Log:

* ``exception_group_key`` - the one canonical identity for a de-duplicated group
  of identical exceptions (same type + entity + period + field). Both the
  workbench report and the TS Exception Disposition controller derive the key
  here so they never drift.
* ``get_open_exceptions`` - grouped, de-duplicated open (and optionally disposed)
  exceptions by entity / period / type, each with its count and disposition.
* ``dispose`` - create/update a TS Exception Disposition for a whole group,
  waiving (with a reason) or resolving it. Never edits the immutable log row.

The disposition write goes through the normal permission system (the caller must
hold create/write on TS Exception Disposition), so no ``ignore_permissions``.
"""

from __future__ import annotations

import hashlib
from typing import Optional

import frappe
from frappe import _
from frappe.utils import cint

EXCEPTION_LOG_DOCTYPE = "Timesheet Exception Log"
DISPOSITION_DOCTYPE = "TS Exception Disposition"
GROUP_AXES = ("exception_type", "entity", "period_month", "field_ref")


def exception_group_key(
    exception_type: str,
    entity: str,
    period_month: Optional[str] = None,
    field_ref: Optional[str] = None,
) -> str:
    """Stable 16-char identity for a group of identical exceptions."""
    raw = "|".join(
        (exception_type or "", entity or "", period_month or "", field_ref or "")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def get_grouped_exceptions(filters: Optional[dict] = None) -> list:
    """Group the exception log by the dedup axes and left-join dispositions.

    Shared by the whitelisted API and the workbench report so both surfaces see
    the identical grouping + disposition state.
    """
    filters = filters or {}
    log_filters = {}
    for axis in ("exception_type", "severity", "entity", "period_month"):
        if filters.get(axis):
            log_filters[axis] = filters[axis]

    rows = frappe.get_all(
        EXCEPTION_LOG_DOCTYPE,
        filters=log_filters,
        fields=[
            "exception_type", "severity", "entity", "period_month", "field_ref",
            "detail", "detected_at",
        ],
        order_by="detected_at desc",
    )

    groups: dict = {}
    for r in rows:
        key = exception_group_key(r.exception_type, r.entity, r.period_month, r.field_ref)
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "group_key": key,
                "exception_type": r.exception_type,
                "severity": r.severity,
                "entity": r.entity,
                "period_month": r.period_month,
                "field_ref": r.field_ref,
                "sample_detail": r.detail,
                "latest_detected_at": r.detected_at,
                "occurrences": 1,
            }
        else:
            g["occurrences"] += 1
            if r.detected_at and (not g["latest_detected_at"] or r.detected_at > g["latest_detected_at"]):
                g["latest_detected_at"] = r.detected_at
                g["sample_detail"] = r.detail

    dispositions = {
        d.group_key: d
        for d in frappe.get_all(
            DISPOSITION_DOCTYPE,
            fields=["group_key", "disposition", "disposed_by", "disposed_at", "reason"],
        )
    }

    include_disposed = cint(filters.get("include_disposed"))
    out = []
    for g in groups.values():
        disp = dispositions.get(g["group_key"])
        g["disposition"] = disp.disposition if disp else "Open"
        g["disposed_by"] = disp.disposed_by if disp else None
        g["reason"] = disp.reason if disp else None
        if disp and not include_disposed:
            continue
        out.append(g)

    out.sort(key=lambda x: (x["severity"] != "GATE", -(x["occurrences"] or 0)))
    return out


@frappe.whitelist()
def get_open_exceptions(
    exception_type=None, severity=None, entity=None, period_month=None, include_disposed=0
) -> list:
    """Whitelisted read surface backing the exception workbench."""
    return get_grouped_exceptions(
        {
            "exception_type": exception_type,
            "severity": severity,
            "entity": entity,
            "period_month": period_month,
            "include_disposed": include_disposed,
        }
    )


@frappe.whitelist(methods=["POST"])
def dispose(
    exception_type, entity, disposition, reason=None, period_month=None, field_ref=None
) -> str:
    """Waive or resolve an exception group. Idempotent per group: an existing
    disposition for the same group is updated, not duplicated. Returns its name."""
    if disposition not in ("Waived", "Resolved"):
        frappe.throw(_("Disposition must be Waived or Resolved."))

    key = exception_group_key(exception_type, entity, period_month, field_ref)
    existing = frappe.db.exists(DISPOSITION_DOCTYPE, {"group_key": key})
    if existing:
        doc = frappe.get_doc(DISPOSITION_DOCTYPE, existing)
    else:
        doc = frappe.new_doc(DISPOSITION_DOCTYPE)
        doc.exception_type = exception_type
        doc.entity = entity
        doc.period_month = period_month
        doc.field_ref = field_ref

    # [#7r7eal]
    frappe.has_permission(
        DISPOSITION_DOCTYPE, "write" if existing else "create", doc=doc, throw=True
    )
    doc.disposition = disposition
    doc.reason = reason
    # [#3v234f]
    doc.save()
    return doc.name
