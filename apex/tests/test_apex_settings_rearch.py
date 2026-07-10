# Copyright (c) 2026, AFMCO and contributors
"""P-091 Apex Settings re-architecture guards.

Three independent pieces, each verified in isolation:

* RETENTION (Move 6) — ``retention_days`` falls back to the built-in literal when
  the Apex Settings Int is unset/zero (the new-Single-Int-stores-0 trap), reads a
  real stored value, and ``effective_retention_days`` reconciles the Log Settings
  invocation: an untouched hook-default seed yields to the Apex Settings value
  while an explicit operator override is honoured.
* PAYMENT METHOD (Move 3) — the lease's payment target resolves from the Payment
  Routing router, defaulting to the native Payment Request when unconfigured.
* COMPANY RESOLVER (Move 2) — ``resolve_company`` walks explicit module setting ->
  user default -> global default and returns None when nothing is configured.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.apex_settings.apex_settings import (
    RETENTION_DEFAULTS,
    effective_retention_days,
    retention_days,
)
from apex.apex_core.payment_router import get_target_payment_doctype
from apex.apex_core.utils.company import resolve_company


def _set_single(doctype, field, value):
    frappe.db.set_single_value(doctype, field, value)


class TestRetentionSetting(FrappeTestCase):
    def tearDown(self):
        for key in RETENTION_DEFAULTS:
            _set_single("Apex Settings", key, 0)

    def test_unset_falls_back_to_literal_not_zero(self):
        # A new Int on an existing Single stores 0; the helper must NOT return 0.
        for key, default in RETENTION_DEFAULTS.items():
            _set_single("Apex Settings", key, 0)
            self.assertEqual(retention_days(key), default)

    def test_stored_value_wins(self):
        _set_single("Apex Settings", "alert_retention_days", 120)
        self.assertEqual(retention_days("alert_retention_days"), 120)

    def test_effective_uses_setting_when_none_passed(self):
        _set_single("Apex Settings", "alert_retention_days", 200)
        self.assertEqual(effective_retention_days("alert_retention_days", None), 200)

    def test_effective_setting_overrides_untouched_hook_seed(self):
        # Log Settings seeds days=90 (the hook default); the setting must win.
        _set_single("Apex Settings", "alert_retention_days", 45)
        self.assertEqual(effective_retention_days("alert_retention_days", 90), 45)

    def test_effective_honours_explicit_operator_override(self):
        # An operator who edits the Log Settings row to a non-default value wins.
        _set_single("Apex Settings", "alert_retention_days", 45)
        self.assertEqual(effective_retention_days("alert_retention_days", 17), 17)

    def test_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            retention_days("not_a_field")


class TestPaymentTargetResolution(FrappeTestCase):
    def setUp(self):
        self._original = frappe.db.get_single_value(
            "Payment Routing Settings", "target_payment_doctype"
        )

    def tearDown(self):
        _set_single("Payment Routing Settings", "target_payment_doctype", self._original)

    def test_defaults_to_payment_request_when_unconfigured(self):
        _set_single("Payment Routing Settings", "target_payment_doctype", None)
        self.assertEqual(get_target_payment_doctype(), "Payment Request")

    def test_resolves_configured_target(self):
        _set_single("Payment Routing Settings", "target_payment_doctype", "Payment Order")
        self.assertEqual(get_target_payment_doctype(), "Payment Order")


class TestResolveCompany(FrappeTestCase):
    def setUp(self):
        self._habitat = frappe.db.get_single_value("Habitat Settings", "company")
        self._salis = frappe.db.get_single_value("Salis Settings", "default_company")
        self._global = frappe.defaults.get_global_default("company")

    def tearDown(self):
        _set_single("Habitat Settings", "company", self._habitat)
        _set_single("Salis Settings", "default_company", self._salis)
        if self._global:
            frappe.defaults.set_global_default("company", self._global)

    def test_explicit_module_setting_wins(self):
        company = self._global or _ensure_company()
        _set_single("Habitat Settings", "company", company)
        self.assertEqual(resolve_company("Habitat"), company)

    def test_salis_reads_its_own_field(self):
        company = self._global or _ensure_company()
        _set_single("Salis Settings", "default_company", company)
        self.assertEqual(resolve_company("Salis"), company)

    def test_falls_back_to_global_default(self):
        company = self._global or _ensure_company()
        frappe.defaults.set_global_default("company", company)
        _set_single("Habitat Settings", "company", None)
        self.assertEqual(resolve_company("Habitat"), company)

    def test_none_when_nothing_configured(self):
        _set_single("Habitat Settings", "company", None)
        frappe.defaults.clear_default("company", parenttype="__default")
        # No module + no user/global default -> None.
        if not frappe.defaults.get_global_default("company"):
            self.assertIsNone(resolve_company("Habitat"))


def _ensure_company() -> str:
    name = frappe.db.get_value("Company", {}, "name")
    if name:
        return name
    company = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": "Apex Test Co",
            "abbr": "ATC",
            "default_currency": "SAR",
            "country": "Saudi Arabia",
        }
    ).insert(ignore_permissions=True)
    return company.name
