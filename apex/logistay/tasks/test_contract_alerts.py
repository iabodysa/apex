# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.tasks.contract_alerts import _contract_expiry_notice_days

_FIELD = "contract_expiry_notice_days"


class TestContractExpiryNoticeWindow(FrappeTestCase):
    def setUp(self):
        self._previous = frappe.db.get_single_value("Logistay Settings", _FIELD)
        self.addCleanup(self._restore)

    def _restore(self):
        frappe.db.set_single_value("Logistay Settings", _FIELD, self._previous)

    def test_an_untouched_site_keeps_the_shipped_notice(self):
        frappe.db.set_single_value("Logistay Settings", _FIELD, 0)
        self.assertEqual(_contract_expiry_notice_days(), 30)

    def test_the_operator_s_own_window_is_what_the_watch_uses(self):
        frappe.db.set_single_value("Logistay Settings", _FIELD, 45)
        self.assertEqual(_contract_expiry_notice_days(), 45)
