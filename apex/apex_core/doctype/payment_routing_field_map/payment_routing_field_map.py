# Copyright (c) 2026, afmcoltd
"""Payment Routing Field Map (child table).

One row maps a single field onto the target payment DocType the router creates.
Each row is applied as::

    target[target_fieldname] = static_value if is_static else source.get(source_fieldname)

There is no per-row logic here by design; the mapping is interpreted by
``apex_core.payment_router.route_payment`` so the rules stay config-time, not
code-time.
"""

from __future__ import annotations

from frappe.model.document import Document


class PaymentRoutingFieldMap(Document):
    pass
