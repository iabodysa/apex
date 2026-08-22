# Copyright (c) 2026, afmcoltd
"""Contract tests for the stock engine's policy gate.

Covers the Single's five callables: ``validate``, ``policy``,
``assert_posting_allowed``, ``_may_backdate`` and ``store_is_open``.

A Single's values persist across tests even inside the transaction rollback some
paths take, so every field this suite touches is snapshotted in ``setUp`` and
restored via ``addCleanup`` — never assumed to reset itself.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.apex_core.doctype.apex_stock_settings.apex_stock_settings import (
    SETTINGS,
    _may_backdate,
    assert_posting_allowed,
    policy,
    store_is_open,
)
from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_building, make_company

FIELDS = (
    "enable_stock_engine",
    "allow_negative_stock",
    "require_active_store",
    "backdating_days",
    "backdating_role",
    "stock_frozen_upto",
)

class TestApexStockSettings(FrappeTestCase):
    def setUp(self):
        make_company()
        doc = frappe.get_single(SETTINGS)
        self._snapshot = {f: doc.get(f) for f in FIELDS}
        self.addCleanup(self._restore)

    def _restore(self):
        doc = frappe.get_single(SETTINGS)
        doc.update(self._snapshot)
        doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype=SETTINGS)

    def _set(self, **values):
        doc = frappe.get_single(SETTINGS)
        doc.update(values)
        doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype=SETTINGS)
        return doc
    def test_validate_rejects_negative_backdating_days(self):
        doc = frappe.get_single(SETTINGS)
        doc.backdating_days = -1
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_validate_warns_when_role_set_but_window_zero(self):
        frappe.clear_messages()
        doc = frappe.get_single(SETTINGS)
        doc.backdating_days = 0
        doc.backdating_role = "System Manager"
        doc.save(ignore_permissions=True)
        msgs = " ".join(m.get("message", "") for m in frappe.get_message_log())
        self.assertIn("no effect", msgs.lower())
    def test_policy_reflects_current_settings(self):
        self._set(
            enable_stock_engine=1,
            allow_negative_stock=1,
            require_active_store=0,
            backdating_days=3,
            backdating_role="System Manager",
            stock_frozen_upto=None,
        )
        p = policy()
        self.assertEqual(
            p,
            {
                "enabled": True,
                "allow_negative": True,
                "backdating_days": 3,
                "backdating_role": "System Manager",
                "frozen_upto": None,
                "require_active_store": False,
            },
        )
    def test_assert_posting_allowed_throws_when_engine_off(self):
        self._set(enable_stock_engine=0)
        with self.assertRaises(frappe.ValidationError):
            assert_posting_allowed(None)

    def test_assert_posting_allowed_throws_on_future_date(self):
        self._set(enable_stock_engine=1, stock_frozen_upto=None, backdating_days=0)
        with self.assertRaises(frappe.ValidationError):
            assert_posting_allowed(None, posting_date=add_days(today(), 1))

    def test_assert_posting_allowed_throws_when_frozen(self):
        self._set(enable_stock_engine=1, stock_frozen_upto=today(), backdating_days=0)
        with self.assertRaises(frappe.ValidationError):
            assert_posting_allowed(None, posting_date=today())

    def test_assert_posting_allowed_passes_within_window(self):
        self._set(
            enable_stock_engine=1,
            stock_frozen_upto=None,
            backdating_days=5,
            require_active_store=0,
        )
        assert_posting_allowed(None, posting_date=today())

    def test_assert_posting_allowed_throws_on_backdating_for_unprivileged_user(self):
        self._set(enable_stock_engine=1, stock_frozen_upto=None, backdating_days=1)
        email = _user("a564-stock-nobd@example.com", "Employee")
        with as_user(email):
            with self.assertRaises(frappe.ValidationError):
                assert_posting_allowed(None, posting_date=add_days(today(), -5))

    def test_assert_posting_allowed_throws_when_store_closed(self):
        building = make_building(name="A564 Closed Store Building", is_procurement_store=1, store_is_active=0)
        self._set(enable_stock_engine=1, stock_frozen_upto=None, backdating_days=5, require_active_store=1)
        with self.assertRaises(frappe.ValidationError):
            assert_posting_allowed(building.name, posting_date=today())

    def test_assert_posting_allowed_passes_when_store_open(self):
        building = make_building(name="A564 Open Store Building", is_procurement_store=1, store_is_active=1)
        self._set(enable_stock_engine=1, stock_frozen_upto=None, backdating_days=5, require_active_store=1)
        assert_posting_allowed(building.name, posting_date=today())
    def test_may_backdate_true_for_system_manager(self):
        self.assertTrue(_may_backdate("Some Role That Does Not Exist"))

    def test_may_backdate_false_for_unprivileged_user_without_role(self):
        email = _user("a564-stock-maybd@example.com", "Employee")
        with as_user(email):
            self.assertFalse(_may_backdate("System Manager"))
    def test_store_is_open_false_for_empty_building(self):
        self.assertFalse(store_is_open(None))

    def test_store_is_open_true_when_active_procurement_store(self):
        building = make_building(name="A564 Store Open", is_procurement_store=1, store_is_active=1)
        self.assertTrue(store_is_open(building.name))

    def test_store_is_open_false_when_inactive(self):
        building = make_building(name="A564 Store Inactive", is_procurement_store=1, store_is_active=0)
        self.assertFalse(store_is_open(building.name))

    def test_store_is_open_false_when_not_procurement_store(self):
        building = make_building(name="A564 Store Not Procurement", is_procurement_store=0, store_is_active=1)
        self.assertFalse(store_is_open(building.name))
