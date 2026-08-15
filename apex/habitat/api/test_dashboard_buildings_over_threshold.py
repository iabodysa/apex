# Copyright (c) 2026, AFMCO and contributors
"""Row-relative card: counts buildings whose occupancy exceeds their OWN
threshold (zero/unset falls back to the 120 default). Stored Percent columns are
forced via db.set_value (validate would recompute); asserts are delta-based so
they don't collide with pre-existing rows."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.dashboard import get_buildings_over_threshold
from apex.tests._helpers import as_user


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


# Bare-count unwrapper. Named apart from the production method it wraps:
# a module-level shim sharing the API's own name reads as a redefinition.
def _buildings_over_threshold_value():
    return get_buildings_over_threshold()["value"]


class TestBuildingsOverThreshold(FrappeTestCase):
    def setUp(self):
        self._names = []
        self.baseline = _buildings_over_threshold_value()

    def _building(self, occupancy, threshold):
        """Insert a building and force the two stored Percent columns directly."""
        doc = frappe.get_doc({
            "doctype": "Building",
            "building_name": "BLDG-" + _h(),
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Building",
            doc.name,
            {"occupancy_percent": occupancy, "over_capacity_threshold_percent": threshold},
            update_modified=False,
        )
        self._names.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._names:
            frappe.delete_doc("Building", name, force=True,
                              ignore_permissions=True)

    def test_counts_only_buildings_over_their_own_threshold(self):
        self._building(occupancy=130, threshold=120)
        self._building(occupancy=120, threshold=120)
        self._building(occupancy=90, threshold=120)
        self._building(occupancy=110, threshold=150)

        delta = _buildings_over_threshold_value() - self.baseline
        self.assertEqual(delta, 1,
                         "only the building strictly over its own threshold is counted")

    def test_unset_threshold_falls_back_to_default_not_zero(self):
        self._building(occupancy=50, threshold=0)
        self.assertEqual(_buildings_over_threshold_value() - self.baseline, 0,
                         "a 0/unset threshold falls back to 120 and is not over")

        self._building(occupancy=130, threshold=0)
        self.assertEqual(_buildings_over_threshold_value() - self.baseline, 1,
                         "occupancy over the 120 default counts when threshold unset")

    def test_returns_number_card_dict_contract(self):
        res = get_buildings_over_threshold()
        self.assertIsInstance(res, dict, "Custom Number Card returns a dict, not a scalar")
        self.assertIn("value", res, "the number must live under the 'value' key")
        self.assertIsInstance(res["value"], int)
        self.assertGreaterEqual(res["value"], 0)
        self.assertEqual(res.get("fieldtype"), "Int")


class TestBuildingsOverThresholdScope(FrappeTestCase):
    """Building row-scope for the over-capacity card.

    The count runs on ``frappe.qb``, which never consults
    ``permission_query_conditions``. The estate axis here is the Building's OWN
    name rather than a ``building`` link, so an over-capacity building outside a
    supervisor's User Permissions would otherwise still be counted for them.
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
        doc = frappe.get_doc({"doctype": "Building", "building_name": "BOT-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role, building=None):
        email = "bot-{0}@example.com".format(_h()).lower()
        frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "Bot",
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
        self.addCleanup(self._reset_occupancy)

    def _reset_occupancy(self):
        for name in (self.b1, self.b2):
            frappe.db.set_value(
                "Building", name,
                {"occupancy_percent": 0, "over_capacity_threshold_percent": 0},
                update_modified=False,
            )

    def _over_capacity(self, building):
        """Force the two stored Percent columns past the threshold directly."""
        frappe.db.set_value(
            "Building", building,
            {"occupancy_percent": 130, "over_capacity_threshold_percent": 120},
            update_modified=False,
        )

    def test_other_building_over_threshold_not_counted_for_scoped_user(self):
        with as_user(self.scoped):
            scoped_base = _buildings_over_threshold_value()
        with as_user(self.oversight):
            oversight_base = _buildings_over_threshold_value()

        self._over_capacity(self.b2)

        with as_user(self.scoped):
            self.assertEqual(
                _buildings_over_threshold_value(), scoped_base,
                "an out-of-scope over-capacity building must not be counted",
            )
        with as_user(self.oversight):
            self.assertEqual(
                _buildings_over_threshold_value(), oversight_base + 1,
                "oversight still counts it across estates",
            )

    def test_own_building_over_threshold_is_counted(self):
        """The scope filter is a filter, not a blanket zero."""
        with as_user(self.scoped):
            scoped_base = _buildings_over_threshold_value()
        self._over_capacity(self.b1)
        with as_user(self.scoped):
            self.assertEqual(_buildings_over_threshold_value(), scoped_base + 1)
