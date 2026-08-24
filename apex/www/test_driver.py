# Copyright (c) 2026, Apex contributors


from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import get_or_create_for_driver
from frappe.translate import get_translations_from_csv

from apex.apex_core.doctype.portal_device.portal_device import (
    apply_device_language,
    consume_enrolment_key,
    mark_onboarded,
    set_device_language,
)
from apex.apex_core.utils.portal_identity import DRIVER
from apex.tests.factories import make_test_driver
from apex.www import driver


class TestDriverEnrolmentLanding(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.driver = make_test_driver()
        self.employee = frappe.db.get_value("Salis Driver", self.driver, "employee")
        self.key = self._rearm_key()
        frappe.local.form_dict = frappe._dict()
        frappe.local.flags.redirect_location = None

    def _rearm_key(self) -> str:
        token = get_or_create_for_driver(self.driver)
        raw = token.recover_token()
        frappe.db.set_value(
            "Masar Worker Token",
            token.name,
            {"consumed_on": None, "enabled": 1, "expires_on": frappe.utils.add_days(None, 30)},
            update_modified=False,
        )
        return raw

    def _open(self, **query):
        frappe.local.form_dict = frappe._dict(query)
        return driver.get_context(frappe._dict())

    def test_a_consumed_enrolment_key_redirects_to_the_permanent_employee_link(self):
        with self.assertRaises(frappe.Redirect):
            self._open(d=self.key)

        self.assertEqual(frappe.local.flags.redirect_location, f"/driver/?id={self.employee}")

    def test_a_second_device_on_an_already_consumed_key_is_refused(self):
        with self.assertRaises(frappe.Redirect):
            self._open(d=self.key)
        frappe.local.flags.redirect_location = None

        with self.assertRaises(frappe.Redirect):
            self._open(d=self.key)

        self.assertEqual(frappe.local.flags.redirect_location, "/driver/")

    def test_the_permanent_link_alone_carries_no_authority(self):
        seen = {}
        with patch.object(
            driver,
            "publish_portal_context",
            side_effect=lambda context, **kwargs: seen.update(kwargs) or context,
        ):
            self._open(id=self.employee)

        self.assertEqual(seen["capabilities"], ())
        self.assertIsNone(seen["subject"])

    def test_the_language_a_device_chose_decides_what_its_screens_read(self):
        device_token = consume_enrolment_key(DRIVER, self.key)
        source = "Skip to content"
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

        self.assertTrue(set_device_language(DRIVER, device_token, "ar"))
        self.assertEqual(apply_device_language(DRIVER, device_token), "ar")
        arabic = get_translations_from_csv("ar", "apex")
        self.assertTrue(arabic.get(source) and arabic[source] != source)

        self.assertTrue(set_device_language(DRIVER, device_token, "en"))
        self.assertEqual(apply_device_language(DRIVER, device_token), "en")
        self.assertNotIn(source, get_translations_from_csv("en", "apex"))

    def test_a_device_that_chose_nothing_reads_the_language_the_site_settled_on(self):
        device_token = consume_enrolment_key(DRIVER, self.key)
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
        self.addCleanup(frappe.db.set_default, "lang", frappe.db.get_default("lang"))

        frappe.db.set_default("lang", "ar")
        self.assertEqual(apply_device_language(DRIVER, device_token), "ar")

    def test_a_device_lands_on_the_walkthrough_until_it_finishes_it(self):
        device_token = consume_enrolment_key(DRIVER, self.key)

        self.assertEqual(driver._initial_route(device_token, self.driver), "/welcome")

        self.assertTrue(mark_onboarded(DRIVER, device_token))
        self.assertEqual(driver._initial_route(device_token, self.driver), "/today")
