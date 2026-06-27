# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DispatchTripAssignedRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		purpose: DF.Data | None
		requested_count: DF.Int
		transport_request: DF.Link
	# end: auto-generated types
	pass
