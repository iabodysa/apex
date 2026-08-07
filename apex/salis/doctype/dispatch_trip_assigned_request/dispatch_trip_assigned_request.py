# Copyright (c) 2026, afmcoltd

from frappe.model.document import Document


class DispatchTripAssignedRequest(Document):

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        purpose: DF.Data | None
        requested_count: DF.Int
        transport_request: DF.Link
    pass
