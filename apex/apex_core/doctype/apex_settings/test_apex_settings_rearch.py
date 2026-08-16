# Copyright (c) 2026, afmcoltd
""" Apex Settings re-architecture guards.

Three independent pieces, each verified in isolation:

* RETENTION (Move 6) — ``retention_days`` falls back to the built-in literal when the Apex
  Settings Int is unset/zero (the new-Single-Int-stores-0 trap), reads a real stored value,
  and ``effective_retention_days`` reconciles the Log Settings invocation: an untouched
  hook-default seed yields to the Apex Settings value while an explicit operator override
  is honoured.
* PAYMENT METHOD (Move 3) — the lease's payment target resolves from the Payment Routing
  router, defaulting to the native Payment Request when unconfigured.
* COMPANY RESOLVER (Move 2) — ``resolve_company`` walks explicit module setting -> user
  default -> global default and returns None when nothing is configured.

The company is ERPNext's ``_Test Company``, named by ``test_dependencies``. The previous
form of this file carried a ``_ensure_company()`` fallback that minted an "Apex Test Co"
whenever the site happened to hold none — a second Company definition living in a test,
which is exactly what a fixture exists to prevent.

Every Single value these cases write is read back from the site first and restored
afterwards: ``frappe.db.set_single_value`` is an ordinary write that the per-class rollback
would undo, but ``frappe.defaults`` also writes through a cache the rollback does not
reach, so the restore is explicit rather than inherited.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.apex_settings.apex_settings import (
    RETENTION_DEFAULTS,
    effective_retention_days,
    retention_days,
)
from apex.apex_core.payment_router import get_target_payment_doctype
from apex.apex_core.utils.company import resolve_company

test_dependencies = ["Company"]

COMPANY = "_Test Company"

# One representative retention key rather than a literal field name: the pre-conversion
# form of this file named ``alert_retention_days``, which the controller no longer defines,
# so four cases raised KeyError the moment the file was first actually run.
RETENTION_KEY = "snapshot_retention_days"


def _set_single(doctype, field, value):
    frappe.db.set_single_value(doctype, field, value)


class TestRetentionSetting(FrappeTestCase):
    def setUp(self):
        for key in RETENTION_DEFAULTS:
            self.addCleanup(_set_single, "Apex Settings", key, 0)

    def test_retention_days_falls_back_to_literal_and_reads_stored_value(self):
        """retention_days treats the Single Int's default (unset/zero) as
        "nothing stored" and falls back to the built-in literal, but reads a
        real stored value back untouched once one exists."""
        for key, default in RETENTION_DEFAULTS.items():
            _set_single("Apex Settings", key, 0)
            self.assertEqual(
                retention_days(key),
                default,
                f"{key}: an unset (zero) Apex Settings Int falls back to the literal default",
            )

        _set_single("Apex Settings", RETENTION_KEY, 120)
        self.assertEqual(
            retention_days(RETENTION_KEY),
            120,
            "a real stored value is read back rather than the literal default",
        )

    def test_effective_retention_days_reconciles_passed_value_against_setting(self):
        """effective_retention_days reconciles the Log Settings invocation: nothing
        passed or an untouched hook-default seed both yield to the stored Apex
        Settings value, while an explicit operator override still wins."""
        _set_single("Apex Settings", RETENTION_KEY, 45)

        self.assertEqual(
            effective_retention_days(RETENTION_KEY, None),
            45,
            "nothing passed falls through to the stored Apex Settings value",
        )
        # The hook seed is the built-in default itself, read from the module rather than
        # written out, so a changed default cannot silently turn this case into the
        # operator-override case below.
        self.assertEqual(
            effective_retention_days(RETENTION_KEY, RETENTION_DEFAULTS[RETENTION_KEY]),
            45,
            "an untouched hook-default seed still yields to the stored Apex Settings value",
        )
        self.assertEqual(
            effective_retention_days(RETENTION_KEY, 17),
            17,
            "an explicit operator override is honoured over the stored Apex Settings value",
        )

    def test_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            retention_days("not_a_field")


class TestPaymentTargetResolution(FrappeTestCase):
    def setUp(self):
        original = frappe.db.get_single_value(
            "Payment Routing Settings", "target_payment_doctype"
        )
        self.addCleanup(
            _set_single, "Payment Routing Settings", "target_payment_doctype", original
        )

    def test_defaults_to_payment_request_when_unconfigured(self):
        _set_single("Payment Routing Settings", "target_payment_doctype", None)
        self.assertEqual(get_target_payment_doctype(), "Payment Request")

    def test_resolves_configured_target(self):
        _set_single("Payment Routing Settings", "target_payment_doctype", "Payment Order")
        self.assertEqual(get_target_payment_doctype(), "Payment Order")


class TestResolveCompany(FrappeTestCase):
    def setUp(self):
        habitat = frappe.db.get_single_value("Habitat Settings", "company")
        salis = frappe.db.get_single_value("Salis Settings", "default_company")
        self.global_default = frappe.defaults.get_global_default("company")

        self.addCleanup(_set_single, "Habitat Settings", "company", habitat)
        self.addCleanup(_set_single, "Salis Settings", "default_company", salis)
        self.addCleanup(self._restore_global_default, self.global_default)

    @staticmethod
    def _restore_global_default(value):
        if value:
            frappe.defaults.set_global_default("company", value)
        else:
            frappe.defaults.clear_default("company", parenttype="__default")

    def test_explicit_module_setting_wins(self):
        _set_single("Habitat Settings", "company", COMPANY)
        self.assertEqual(resolve_company("Habitat"), COMPANY)

    def test_salis_reads_its_own_field(self):
        _set_single("Salis Settings", "default_company", COMPANY)
        self.assertEqual(resolve_company("Salis"), COMPANY)

    def test_falls_back_to_global_default(self):
        frappe.defaults.set_global_default("company", COMPANY)
        _set_single("Habitat Settings", "company", None)
        self.assertEqual(resolve_company("Habitat"), COMPANY)

    def test_none_when_nothing_configured(self):
        _set_single("Habitat Settings", "company", None)
        frappe.defaults.clear_default("company", parenttype="__default")
        self.assertIsNone(resolve_company("Habitat"))
