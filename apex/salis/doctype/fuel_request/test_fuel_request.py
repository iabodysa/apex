# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.fuel_request.fuel_request import FuelRequest


class TestFuelRequest(FrappeTestCase):
    def test_explicit_blank_request_type_is_not_silently_defaulted(self):
        request = FuelRequest(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "status": "Pending",
                "requested_by": "Administrator",
            }
        )
        request.request_type = None

        with (
            patch.object(FuelRequest, "_validate_standard"),
            patch.object(FuelRequest, "_enforce_rider_active"),
            patch.object(FuelRequest, "_guard_initial_status"),
            patch.object(FuelRequest, "_stamp_approver"),
            self.assertRaisesRegex(frappe.ValidationError, "Invalid Request Type"),
        ):
            request.validate()
