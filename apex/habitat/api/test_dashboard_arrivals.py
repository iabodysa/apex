# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Arrivals telemetry Number Card methods get_arrivals_today and
get_pending_on_manifest. Each case scopes to a unique building so the asserts are
exact regardless of pre-existing site data. Assignments are inserted directly and
forced to docstatus=1 + check_in_date via db.set_value (validate would otherwise
run the bed-lock/occupancy gates) — the same direct approach the sibling
dashboard tests use."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.api.dashboard import get_arrivals_today, get_pending_on_manifest
from apex.tests._helpers import as_user


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


# [#aqvzq8] Bare-count unwrappers. Named apart from the production methods they
# wrap: a module-level shim sharing the API's own name reads as a redefinition.
def _arrivals_today_value():
    return get_arrivals_today()["value"]


def _pending_on_manifest_value():
    return get_pending_on_manifest()["value"]


class TestDashboardArrivals(FrappeTestCase):
    def setUp(self):
        self.today = today()
        self.yesterday = add_days(self.today, -1)
        self.building = "BLDG-" + _h()
        self._assignments = []
        self._batches = []

    def _assignment(self, check_in_date, building=None):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Employee",
            "party": "EMP-" + _h(),
            "employee": "EMP-" + _h(),
            "building": building or self.building,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Housing Assignment", doc.name,
            {"docstatus": 1, "check_in_date": check_in_date}, update_modified=False,
        )
        self._assignments.append(doc.name)
        return doc.name

    def _batch(self, expected_date, expected_n, building=None):
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": building or self.building,
            "expected_date": expected_date,
            "expected_workers": [
                {"worker_name": "W-" + _h(), "passport_number": "P" + _h(12)}
                for _ in range(expected_n)
            ],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self._batches.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._assignments:
            frappe.db.set_value("Housing Assignment", name, "docstatus", 0,
                                update_modified=False)
            frappe.delete_doc("Housing Assignment", name, force=True,
                              ignore_permissions=True)
        for name in self._batches:
            frappe.delete_doc("Arrival Batch", name, force=True, ignore_permissions=True)

    # [#t5shhz]

    def test_arrivals_today_counts_only_today_submitted(self):
        """Only today's submitted check-ins are counted; yesterday's is excluded."""
        base = _arrivals_today_value()
        self._assignment(self.today)
        self._assignment(self.today)
        self._assignment(self.yesterday)  # [#c5x40g]
        self.assertEqual(_arrivals_today_value(), base + 2)

    def test_arrivals_today_ignores_draft(self):
        """A draft (docstatus=0) check-in dated today is not counted."""
        base = _arrivals_today_value()
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Employee",
            "party": "EMP-" + _h(),
            "employee": "EMP-" + _h(),
            "building": self.building,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value("Housing Assignment", doc.name, "check_in_date",
                            self.today, update_modified=False)
        self._assignments.append(doc.name)
        self.assertEqual(_arrivals_today_value(), base, "draft check-in must not count")

    # [#1xipz0]

    def test_pending_is_expected_minus_housed(self):
        """A due manifest of 3 with 1 housed in the building on its date leaves 2
        pending, mirroring ArrivalBatch.pending_arrival_count."""
        base = _pending_on_manifest_value()
        self._batch(self.yesterday, 3)
        self._assignment(self.yesterday)  # [#9tvtdd]
        self.assertEqual(_pending_on_manifest_value(), base + 2)

    def test_future_manifest_not_yet_pending(self):
        """A manifest whose expected_date is in the future is not counted yet."""
        base = _pending_on_manifest_value()
        self._batch(add_days(self.today, 5), 4)
        self.assertEqual(_pending_on_manifest_value(), base, "future batch excluded")

    def test_over_arrival_clamps_to_zero(self):
        """More housed than expected for one batch clamps that batch to 0 and does
        not offset another batch's shortfall (GREATEST(...,0) per batch)."""
        base = _pending_on_manifest_value()
        # [#p6jslp]
        self._batch(self.yesterday, 1)
        self._assignment(self.yesterday)
        self._assignment(self.yesterday)
        self._assignment(self.yesterday)
        # [#pn7312]
        other_building = "BLDG-" + _h()
        self._batch(self.yesterday, 2, building=other_building)
        self.assertEqual(_pending_on_manifest_value(), base + 2)

    # [#fbphqm]

    def test_cards_return_number_card_dict_contract(self):
        """Both methods return the Custom Number Card {value: n, ...df} dict, not a
        bare scalar (a scalar renders but drops the format docfield)."""
        for res in (get_arrivals_today(), get_pending_on_manifest()):
            self.assertIsInstance(res, dict, "Custom Number Card returns a dict, not a scalar")
            self.assertIn("value", res, "the number must live under the 'value' key")
            self.assertIsInstance(res["value"], int)
            self.assertEqual(res.get("fieldtype"), "Int")


class TestDashboardArrivalsScope(FrappeTestCase):
    """Building row-scope for the two arrivals cards.

    ``get_arrivals_today`` counts through ``frappe.db.count`` and
    ``get_pending_on_manifest`` through raw SQL. Neither path consults
    ``permission_query_conditions``, so the estate filter the Assignment / Batch
    LIST views get is absent and a building-scoped supervisor would otherwise be
    handed an estate-wide number. Rows land in b2 only; a supervisor scoped to b1
    must still read their own pre-b2 baseline while oversight sees the increase.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._user("Resident Supervisor", building=cls.b1)
        cls.oversight = cls._user("Accommodation Manager")

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "ARS-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role, building=None):
        email = "ars-{0}@example.com".format(_h()).lower()
        frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "Ars",
            "send_welcome_email": 0,
            "roles": [{"role": role}],
        }).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        if building:
            up = frappe.get_doc({
                "doctype": "User Permission",
                "user": email,
                "allow": "Building",
                "for_value": building,
            })
            up.insert(ignore_permissions=True)
            cls.addClassCleanup(
                frappe.delete_doc,
                "User Permission",
                up.name,
                force=True,
                ignore_permissions=True,
            )
        return email

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")

    def _assignment(self, building, check_in_date):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Employee",
            "party": "EMP-" + _h(),
            "employee": "EMP-" + _h(),
            "building": building,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Housing Assignment", doc.name,
            {"docstatus": 1, "check_in_date": check_in_date}, update_modified=False,
        )
        self.addCleanup(
            lambda n=doc.name: (
                frappe.db.set_value("Housing Assignment", n, "docstatus", 0,
                                    update_modified=False),
                frappe.delete_doc("Housing Assignment", n, force=True,
                                  ignore_permissions=True),
            )
        )
        return doc.name

    def _batch(self, building, expected_date, expected_n):
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": building,
            "expected_date": expected_date,
            "expected_workers": [
                {"worker_name": "W-" + _h(), "passport_number": "P" + _h(12)}
                for _ in range(expected_n)
            ],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            frappe.delete_doc, "Arrival Batch", doc.name, force=True,
            ignore_permissions=True,
        )
        return doc.name

    def test_arrivals_today_excludes_other_building(self):
        with as_user(self.scoped):
            scoped_base = _arrivals_today_value()
        with as_user(self.oversight):
            oversight_base = _arrivals_today_value()

        self._assignment(self.b2, today())

        with as_user(self.scoped):
            self.assertEqual(
                _arrivals_today_value(), scoped_base,
                "a b2 arrival must not reach a b1-scoped supervisor's card",
            )
        with as_user(self.oversight):
            self.assertEqual(
                _arrivals_today_value(), oversight_base + 1,
                "oversight still counts the arrival across estates",
            )

    def test_arrivals_today_counts_own_building(self):
        """The scope filter is a filter, not a blanket zero."""
        with as_user(self.scoped):
            scoped_base = _arrivals_today_value()
        self._assignment(self.b1, today())
        with as_user(self.scoped):
            self.assertEqual(_arrivals_today_value(), scoped_base + 1)

    def test_pending_on_manifest_excludes_other_building(self):
        yesterday = add_days(today(), -1)
        with as_user(self.scoped):
            scoped_base = _pending_on_manifest_value()
        with as_user(self.oversight):
            oversight_base = _pending_on_manifest_value()

        self._batch(self.b2, yesterday, 3)

        with as_user(self.scoped):
            self.assertEqual(
                _pending_on_manifest_value(), scoped_base,
                "a b2 manifest gap must not reach a b1-scoped supervisor's card",
            )
        with as_user(self.oversight):
            self.assertEqual(
                _pending_on_manifest_value(), oversight_base + 3,
                "oversight still sees the whole estate's manifest gap",
            )

    def test_pending_on_manifest_counts_own_building(self):
        yesterday = add_days(today(), -1)
        with as_user(self.scoped):
            scoped_base = _pending_on_manifest_value()
        self._batch(self.b1, yesterday, 2)
        with as_user(self.scoped):
            self.assertEqual(_pending_on_manifest_value(), scoped_base + 2)
