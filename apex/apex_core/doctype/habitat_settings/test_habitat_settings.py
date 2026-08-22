# Copyright (c) 2026, afmcoltd
"""What Habitat Settings guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_validate``). This is a Single — one standing row shared by the whole suite — so
every case that changes a value restores it with ``self.addCleanup`` before returning.

Three guarantees pinned here: ``retention_days``/``effective_retention_days`` resolve a
blank-or-zero stored window to its built-in default while honouring an explicit override
(the "new-Single-Int-stores-0" trap this app has already been bitten by once, per
``habitat_settings.py``'s own docstring); ``gl_posting_enabled`` reflects the stored flag
exactly; and ``validate`` refuses a Payment Router target that cannot be a real payment
document, fail-closed, before any payment is ever routed against it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.habitat_settings.habitat_settings import (
    effective_retention_days,
    gl_posting_enabled,
    retention_days,
)


class TestHabitatSettings(FrappeTestCase):
    def test_retention_days_falls_back_to_the_default_when_the_stored_value_is_zero(self):
        """An Int field nobody has filled in is stored as 0, and a zero retention window
        would purge every snapshot on the very next daily cleanup — the built-in default
        must win instead."""
        original = frappe.db.get_single_value(
            "Habitat Settings", "snapshot_retention_days"
        )
        self.addCleanup(
            frappe.db.set_single_value,
            "Habitat Settings",
            "snapshot_retention_days",
            original,
        )
        frappe.db.set_single_value("Habitat Settings", "snapshot_retention_days", 0)

        self.assertEqual(retention_days("snapshot_retention_days"), 365)

    def test_effective_retention_days_honours_an_explicit_override(self):
        """Log Settings always calls ``clear_old_logs(days=...)`` with a value seeded
        from the hook default; a caller passing something ELSE is an operator's explicit
        Log Settings edit and must win over the Habitat Settings field, or the setting a
        user edited is silently ignored."""
        self.assertEqual(effective_retention_days("snapshot_retention_days", 999), 999)

    def test_effective_retention_days_uses_the_habitat_settings_value_when_untouched(self):
        """The untouched case — no override passed — must read the Habitat Settings
        field, not silently fall back to the hook's own built-in literal."""
        original = frappe.db.get_single_value(
            "Habitat Settings", "snapshot_retention_days"
        )
        self.addCleanup(
            frappe.db.set_single_value,
            "Habitat Settings",
            "snapshot_retention_days",
            original,
        )
        frappe.db.set_single_value("Habitat Settings", "snapshot_retention_days", 100)

        self.assertEqual(effective_retention_days("snapshot_retention_days", None), 100)

    def test_gl_posting_enabled_reflects_the_stored_flag(self):
        """The Payment Router and the housing ledger both gate their GL side effects on
        this single read; if it drifted from the stored value, financial postings would
        fire (or stay silent) against the operator's actual setting."""
        original = frappe.db.get_single_value("Habitat Settings", "enable_gl_posting")
        self.addCleanup(
            frappe.db.set_single_value,
            "Habitat Settings",
            "enable_gl_posting",
            original,
        )

        frappe.db.set_single_value("Habitat Settings", "enable_gl_posting", 0)
        self.assertFalse(gl_posting_enabled())

        frappe.db.set_single_value("Habitat Settings", "enable_gl_posting", 1)
        self.assertTrue(gl_posting_enabled())

    def test_a_single_settings_doctype_as_the_payment_target_is_refused(self):
        """``target_payment_doctype`` is a Link to DocType, so frappe's own field-level
        link check already refuses a name that does not exist — a name that DOES exist
        but is structurally impossible as a payment (a Single, which ``insert`` would
        overwrite rather than create) is what ``validate_target_doctype`` exists to
        catch, and this is the case that actually reaches it."""
        settings = frappe.get_single("Habitat Settings")
        settings.target_payment_doctype = "Apex Stock Settings"

        with self.assertRaisesRegex(frappe.ValidationError, "Single settings record"):
            settings.save()

    def test_an_unconfigured_payment_target_is_accepted(self):
        """The acceptance counterpart — leaving Target Payment DocType unset (the
        factory default, routing to the native Payment Request) must still save clean."""
        settings = frappe.get_single("Habitat Settings")
        original = settings.target_payment_doctype
        self.addCleanup(
            frappe.db.set_single_value,
            "Habitat Settings",
            "target_payment_doctype",
            original,
        )

        settings.target_payment_doctype = None
        settings.save()

        self.assertFalse(
            frappe.db.get_single_value("Habitat Settings", "target_payment_doctype")
        )
