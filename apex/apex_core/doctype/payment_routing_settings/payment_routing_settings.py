# Copyright (c) 2026, afmcoltd
"""Payment Routing Settings controller.

Single configuration record for the Payment Router. It defines, per deployment:

* ``target_payment_doctype`` - which payment DocType the Pay action creates;
* ``auto_submit_target`` - whether the router submits a submittable target;
* ``field_map`` - the config-time source -> target field mapping (child rows).

This replaces the inert ``Habitat Settings.default_payment_method``. The router
only routes the payment record; GL posting stays governed by
``enable_gl_posting``. The dispatch logic lives in
``apex.apex_core.payment_router`` so the mapping is interpreted at
config time with no hard-coded per-DocType branches here.
"""

from __future__ import annotations

from frappe.model.document import Document


class PaymentRoutingSettings(Document):
    def validate(self):
        """Refuse an unroutable configuration at config time, fail-closed.

        Both guards live in ``apex.apex_core.payment_router`` and are re-run there
        immediately before the insert, because this ``validate`` is skipped by
        ``db_set``, raw SQL and patches. Config-integrity only - nothing is posted
        or created here.
        """
        from apex.apex_core.payment_router import (
            get_target_doctype,
            validate_field_map,
            validate_target_doctype,
        )

        target = get_target_doctype(self)
        validate_target_doctype(target)
        validate_field_map(target, self.field_map or [])
