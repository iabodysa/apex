# Copyright (c) 2026, afmcoltd

"""The role escalation ladder every HR notification enters through.

A ladder, not a union: the second rung is reached only when the first is empty, so a
site that has an HR Manager never copies the site administrator on routine HR traffic.
Returning the union instead would make one escalation permanent once it fired.
"""

from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import role_assignment
from apex.apex_core.utils.role_assignment import role_holders_escalating


class TestRoleHoldersEscalating(FrappeTestCase):
    """The ladder's own branch, with the database layer stood in for.

    ``role_holders`` is exercised by its own callers; what is proved here is the
    choice between rungs, which no site state can demonstrate on a bench whose only
    role holders are Administrator and Guest — both of which ``role_holders`` drops.
    """

    def setUp(self):
        self._real = role_assignment.role_holders

    def tearDown(self):
        role_assignment.role_holders = self._real

    def _holders(self, mapping):
        role_assignment.role_holders = lambda role: mapping.get(role, [])

    def test_the_first_occupied_rung_wins_alone(self):
        self._holders({"HR Manager": ["hr@example.com"], "System Manager": ["sm@example.com"]})
        self.assertEqual(
            role_holders_escalating("HR Manager", "System Manager"), ["hr@example.com"]
        )

    def test_an_empty_first_rung_falls_through(self):
        self._holders({"System Manager": ["sm@example.com"]})
        self.assertEqual(
            role_holders_escalating("HR Manager", "System Manager"), ["sm@example.com"]
        )

    def test_no_occupied_rung_returns_empty_not_none(self):
        self._holders({})
        self.assertEqual(role_holders_escalating("HR Manager", "System Manager"), [])

    def test_order_decides_which_rung_answers(self):
        self._holders({"HR Manager": ["hr@example.com"], "System Manager": ["sm@example.com"]})
        self.assertEqual(
            role_holders_escalating("System Manager", "HR Manager"), ["sm@example.com"]
        )

    def test_guest_is_dropped_by_the_rung_it_would_occupy(self):
        """``role_holders`` removes Guest, so a role granted to Guest alone leaves the
        rung empty rather than making it look occupied."""
        self.assertEqual(self._real.__module__, "apex.apex_core.utils.role_assignment")
        role_assignment.role_holders = self._real
        self.assertNotIn("Guest", role_holders_escalating("Guest"))
