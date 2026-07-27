# Copyright (c) 2026, AFMCO and contributors
"""Camera Access Grant controller.

THE ABSENT APPROVAL CHECK IS A RECORDED DECISION, NOT AN OVERSIGHT.

Owner decision 2026-07-27: one role requests this grant and the same role submits it.
There is deliberately NO ``before_submit`` approval check here and no ``before_submit``
entry in ``hooks.py`` doc_events for this DocType. What was corrected on that date was
the ``approved_by`` field TEXT -- it read as a control while enforcing nothing. It is
now labelled and described as the written record it actually is.

Do not add an approval gate here without a fresh owner decision, and do not restore
wording that implies one. ``test_camera_access_grant_authorization_text`` holds both
halves so this is not re-opened as a defect.
"""

from __future__ import annotations

from frappe.model.document import Document


class CameraAccessGrant(Document):
    pass
