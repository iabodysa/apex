"""Maintenance Inspection Report controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceInspectionReport(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from apex_habitat.habitat.doctype.inspection_finding_item.inspection_finding_item import InspectionFindingItem
        from frappe.types import DF

        amended_from: DF.Link | None
        building: DF.Link
        cancellation_reason: DF.SmallText | None
        findings: DF.Table[InspectionFindingItem]
        inspection_date: DF.Date
        inspection_type: DF.Literal["Pre-Work", "Post-Work", "Periodic", "Emergency"]
        inspector: DF.Link
        maintenance_work_order: DF.Link | None
        naming_series: DF.Literal["MIR-.YYYY.-.####"]
        overall_result: DF.Literal["Pass", "Pass with Observations", "Fail"]
        remarks: DF.SmallText | None
    # end: auto-generated types
    pass


def validate(doc, method=None):
    if not doc.findings:
        frappe.throw(_("At least one finding is required on a Maintenance Inspection Report."))


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Maintenance Inspection Report."))
