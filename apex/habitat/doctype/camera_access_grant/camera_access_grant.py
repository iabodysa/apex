# Copyright (c) 2026, AFMCO and contributors
"""Camera Access Grant controller.

THE ABSENT APPROVAL CHECK IS DELIBERATE, NOT AN OVERSIGHT.

One role requests this grant and the same role submits it. There is deliberately NO
``before_submit`` approval check here and no ``before_submit`` entry in ``hooks.py``
doc_events for this DocType. ``approved_by`` is the written record of an authorization
given outside the system; it enforces nothing, and its label and description say so.

Do not add an approval gate here, and do not restore wording that implies one.
"""

from __future__ import annotations

from frappe.model.document import Document


class CameraAccessGrant(Document):
    pass
