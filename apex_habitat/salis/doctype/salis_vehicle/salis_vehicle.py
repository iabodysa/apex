"""Salis Vehicle controller."""

from __future__ import annotations

from frappe.model.document import Document


class SalisVehicle(Document):
    # NOTE: current_driver mirrors Driver.current_vehicle for quick reference only.
    # Vehicle Assignment is the authoritative source of the vehicle<->driver pairing.
    def validate(self):
        self._set_plate_normalized()

    def _set_plate_normalized(self):
        if self.plate_number:
            self.plate_normalized = "".join(self.plate_number.split()).upper()
        else:
            self.plate_normalized = None
