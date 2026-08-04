# Copyright (c) 2026, AFMCO and contributors

from frappe.model.document import Document


class TransportTripRating(Document):

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        dispatch_trip: DF.Link
        employee: DF.Link
        feedback: DF.SmallText | None
        naming_series: DF.Literal["TTR-.####"]
        rating: DF.Rating
        transport_request: DF.Link | None
    pass
