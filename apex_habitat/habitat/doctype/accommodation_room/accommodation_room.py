"""Accommodation Room controller."""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationRoom(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        bed_capacity: DF.Int
        building: DF.Link
        current_occupancy: DF.Int
        floor: DF.Int
        inventory_notes: DF.SmallText | None
        last_inventory_date: DF.Date | None
        naming_series: DF.Literal["ROOM-.####"]
        readiness_status: DF.Literal["Unknown", "Ready", "Needs Cleaning", "Needs Repair", "Out of Service"]
        room_number: DF.Data
        room_type: DF.Literal["Standard", "Worker", "Driver", "Supervisor", "Office", "Storage", "Isolation", "Maintenance", "Other"]
        status: DF.Literal["Available", "Partially Occupied", "Full", "Under Maintenance"]
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
