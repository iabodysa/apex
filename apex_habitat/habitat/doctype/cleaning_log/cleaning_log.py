"""Cleaning Log controller."""

from __future__ import annotations

from frappe.model.document import Document


class CleaningLog(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from apex_habitat.habitat.doctype.cleaning_log_room_detail.cleaning_log_room_detail import CleaningLogRoomDetail
        from frappe.types import DF

        approver: DF.Link | None
        building: DF.Link
        cleaned_by: DF.Data | None
        cleaner_employee: DF.Link | None
        cleaner_type: DF.Literal["Internal Employee", "Subcontractor", "External Worker"]
        cleaning_date: DF.Date
        evidence_notes: DF.SmallText | None
        evidence_photo: DF.AttachImage | None
        missed_cleaning: DF.Check
        missed_reason: DF.Data | None
        naming_series: DF.Literal["CLEAN-.YYYY.-.####"]
        rework_required: DF.Check
        room_details: DF.Table[CleaningLogRoomDetail]
        scheduled_task_instance: DF.Link | None
        subcontractor_service_order: DF.Link | None
        supervisor_approved: DF.Check
        supervisor_rating: DF.Literal["", "Satisfactory", "Needs Improvement", "Unsatisfactory"]
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
