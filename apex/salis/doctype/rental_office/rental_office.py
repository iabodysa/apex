# Copyright (c) 2026, afmcoltd
"""Rental Office controller.

THE OWN FIELDS ARE THE ADDRESS. ``city``, ``contact_person`` and ``phone`` on this
DocType are where an office's contact details live, and the native Address/Contact
panel was removed rather than kept beside them.

The reason is the data, measured rather than assumed: every Rental Office in service
carries the Data fields and NONE carries a linked Address or Contact, and no patch has
ever moved a value from one shape to the other. The panel
was wired and had gone unused since it was added, so it was not a second source of
truth — it was a second place to type that nobody had typed into. Keeping both would
have left the operator two forms for one fact; making the Data fields read-only would
have hidden the only values that exist.

A rental office is one branch of a Supplier and carries one city and one phone. If it
ever needs a full postal address, a country or several sites, the native shape is the
right answer and this decision should be revisited WITH a backfill — not by re-adding
the panel and letting the two drift.
"""

from __future__ import annotations

from frappe.model.document import Document


class RentalOffice(Document):
    def validate(self):
        """Trims the office name so the stored value matches the name frappe derives from it."""
        if self.office_name:
            self.office_name = self.office_name.strip()
