# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# [#j03s5a]

# [#keeppb]
from frappe.model.document import Document


class TransportTripRating(Document):
    # [#q6y9j5]

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        dispatch_trip: DF.Link
        employee: DF.Link
        feedback: DF.SmallText | None
        naming_series: DF.Literal["TTR-.####"]
        rating: DF.Rating
        transport_request: DF.Link | None
    # [#g4leg3]
    pass
