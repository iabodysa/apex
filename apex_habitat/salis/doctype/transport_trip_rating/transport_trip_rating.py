# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class TransportTripRating(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		dispatch_trip: DF.Link
		employee: DF.Link
		feedback: DF.SmallText | None
		naming_series: DF.Literal["TTR-.####"]
		rating: DF.Rating
		transport_request: DF.Link | None
	# end: auto-generated types
	pass
