# Copyright (c) 2026, afmcoltd
"""Logistay Settings controller.

Single DocType holding the telecom module's operator-editable numbers. It exists
because Logistay ships operational alert windows whose siblings in Habitat and
Salis already sit in a Single, and an operator who wants a different notice
period must not need a code change to get one.

No ``validate``: every field here is a plain window an operator sets, and the
reader applies the fallback when the field is unset.
"""

from __future__ import annotations

from frappe.model.document import Document


class LogistaySettings(Document):
    pass
