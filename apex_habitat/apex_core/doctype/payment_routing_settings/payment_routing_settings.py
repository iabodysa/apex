"""Payment Routing Settings controller.

Single configuration record for the Payment Router. It defines, per deployment:

* ``target_payment_doctype`` - which payment DocType the Pay action creates;
* ``auto_submit_target`` - whether the router submits a submittable target;
* ``field_map`` - the config-time source -> target field mapping (child rows).

This replaces the inert ``Habitat Settings.default_payment_method``. The router
only routes the payment record; GL posting stays governed by
``enable_gl_posting``. The dispatch logic lives in
``apex_habitat.apex_core.payment_router`` so the mapping is interpreted at
config time with no hard-coded per-DocType branches here.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class PaymentRoutingSettings(Document):
    def validate(self):
        self._validate_field_map()

    def _validate_field_map(self):
        """Guard obvious config mistakes before the router relies on the rows.

        Every row must name a target field. A non-static row must name a source
        field to copy from; a static row must carry a static value. These are
        config-integrity checks only - they post nothing and create nothing.
        """
        seen = set()
        for row in self.field_map or []:
            target = (row.target_fieldname or "").strip()
            if not target:
                frappe.throw(
                    _("Field Map row {0}: Target Fieldname is required.").format(row.idx)
                )
            if target in seen:
                frappe.throw(
                    _("Field Map row {0}: Target Fieldname {1} is mapped more than once.").format(
                        row.idx, target
                    )
                )
            seen.add(target)
            if row.is_static:
                # A static row writes static_value (which may legitimately be an
                # empty string only if intentional); require the source to be
                # blank so the intent is unambiguous.
                if (row.source_fieldname or "").strip():
                    frappe.throw(
                        _("Field Map row {0}: clear Source Fieldname on a Static row.").format(
                            row.idx
                        )
                    )
            elif not (row.source_fieldname or "").strip():
                frappe.throw(
                    _("Field Map row {0}: Source Fieldname is required when the row is not Static.").format(
                        row.idx
                    )
                )


def get_routing_settings() -> Document:
    """Return the Payment Routing Settings single document."""
    return frappe.get_single("Payment Routing Settings")
