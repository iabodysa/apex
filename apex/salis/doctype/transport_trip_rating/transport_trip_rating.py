# Copyright (c) 2026, afmcoltd

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


def on_doctype_update():
    """One rating per worker per trip, enforced by the database rather than by a
    read-then-insert that two taps can both pass."""
    from apex.apex_core.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Transport Trip Rating",
        ["employee", "dispatch_trip"],
        constraint_name="unique_ttr_employee_trip",
    )
