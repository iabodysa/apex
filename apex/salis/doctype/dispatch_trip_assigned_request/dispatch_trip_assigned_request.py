# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# [#j03s5a]

# [#keeppb]
from frappe.model.document import Document


class DispatchTripAssignedRequest(Document):
    # [#q6y9j5]

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        purpose: DF.Data | None
        requested_count: DF.Int
        transport_request: DF.Link
    # [#g4leg3]
    pass
