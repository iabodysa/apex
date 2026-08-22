# Copyright (c) 2026, afmcoltd
"""What a Route Plan guarantees, asserted against the DocType itself.

Every stop must carry a name, and ``total_stops`` is always recomputed from
the stops table rather than trusted as typed. A brand-new plan must name its
project — a plan with no project is invisible to every project-scoped
supervisor — though existing untagged plans are left alone (the rule is
insert-only, not a blanket ``reqd``). Submitting stamps the acting user as
``movement_planner``.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver", "Project"]


class TestRoutePlan(FrappeTestCase):
    def test_a_stop_without_a_name_is_refused(self):
        """An unnamed stop cannot be shown to a driver or a supervisor."""
        plan = frappe.copy_doc(frappe.get_test_records("Route Plan")[0])
        plan.append("stops", {"stop_name": ""})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Stop Name is required",
            plan.insert,
        )

    def test_total_stops_is_recomputed_from_the_stops_table(self):
        """A hand-set stop count must not survive save; it always reflects the real rows."""
        plan = frappe.copy_doc(frappe.get_test_records("Route Plan")[0])
        plan.total_stops = 999
        plan.append("stops", {"stop_name": "Camp Gate"})
        plan.append("stops", {"stop_name": "Site Office"})
        plan.insert()
        self.assertEqual(plan.total_stops, 2)

    def test_a_new_plan_without_a_project_is_refused(self):
        """A plan with no project is invisible to every project-scoped supervisor."""
        plan = frappe.copy_doc(frappe.get_test_records("Route Plan")[0])
        plan.project = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must name its project",
            plan.insert,
        )

    def test_submitting_a_plan_stamps_the_acting_user_as_movement_planner(self):
        """The plan must record who at Movement actually fulfilled the request."""
        plan = frappe.copy_doc(frappe.get_test_records("Route Plan")[0])
        plan.insert()
        plan.submit()
        self.assertEqual(plan.movement_planner, frappe.session.user)
