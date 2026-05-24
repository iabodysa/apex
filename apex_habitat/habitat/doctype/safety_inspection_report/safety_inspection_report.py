"""Safety Inspection Report controller."""

from __future__ import annotations

from frappe.model.document import Document


class SafetyInspectionReport(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from apex_habitat.habitat.doctype.inspection_finding_item.inspection_finding_item import InspectionFindingItem
        from apex_habitat.habitat.doctype.linked_maintenance_request_item.linked_maintenance_request_item import LinkedMaintenanceRequestItem
        from frappe.types import DF

        amended_from: DF.Link | None
        building: DF.Link
        inspection_date: DF.Date
        inspector: DF.Link
        linked_maintenance_requests: DF.Table[LinkedMaintenanceRequestItem]
        maintenance_findings: DF.Table[InspectionFindingItem]
        naming_series: DF.Literal["FSI-.YYYY.-.#####"]
        previous_repair_notes: DF.SmallText | None
        previous_repairs_confirmed: DF.Check
        safety_findings: DF.Table[InspectionFindingItem]
        safety_section_clear: DF.Check
        submitted_to: DF.SmallText | None
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
