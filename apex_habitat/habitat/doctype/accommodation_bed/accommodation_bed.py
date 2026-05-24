"""Accommodation Bed controller. Smallest atomic spatial unit."""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationBed(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        bed_code: DF.Data
        building: DF.Link | None
        condition: DF.Literal["Good", "Needs Repair", "Scrapped"]
        last_inspected: DF.Date | None
        naming_series: DF.Literal["BED-.####"]
        room: DF.Link
        status: DF.Literal["Available", "Occupied", "Out of Service"]
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
