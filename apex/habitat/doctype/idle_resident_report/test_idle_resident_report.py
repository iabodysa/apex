# Copyright (c) 2026, afmcoltd
"""What Idle Resident Report guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is the module-level
``validate`` wired in ``hooks.py``. It refuses a second open (Open/Acknowledged) report
for an employee who already has one standing, and stamps the acknowledge/resolve audit
fields the moment their status is reached — never leaving a Resolved report without a
resolver, or an Acknowledged one without an acknowledger. ``after_insert``'s role-queue
ToDo delegates to the shared, cross-cutting ``assign_role``/building-scope permission
check and is out of scope for a test of this DocType's own contract.

Each case is pinned to its own ``_T-Employee-0000N``: this DocType's own guard is
keyed on "one open report per employee", and this test class shares one transaction
across its methods (`FrappeTestCase` rolls back once at class teardown), so two cases
sharing an employee would trip each other's guard. Only three test employees ship with
the app, so a case that must leave its report standing Open takes one for itself, and
one that does not is written to resolve its report before returning it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Employee"]


def _new_report(employee):
    record = frappe.copy_doc(frappe.get_test_records("Idle Resident Report")[0])
    record.employee = employee
    record.insert()
    return record


class TestIdleResidentReport(FrappeTestCase):
    def test_a_new_report_is_accepted_once_the_earlier_one_is_resolved(self):
        """The one-open-report guard is scoped to Open/Acknowledged, not to the employee forever."""
        first = _new_report("_T-Employee-00001")
        first.status = "Resolved"
        first.resolution_notes = "Deployed to a new assignment"
        first.save()

        second = _new_report("_T-Employee-00001")

        self.assertEqual(second.status, "Open")

    def test_a_second_open_report_for_the_same_employee_is_refused(self):
        """One employee cannot have two live idle reports open at once."""
        _new_report("_T-Employee-00002")

        second = frappe.copy_doc(frappe.get_test_records("Idle Resident Report")[0])
        second.employee = "_T-Employee-00002"
        with self.assertRaisesRegex(frappe.ValidationError, "already exists for employee"):
            second.insert()

    def test_acknowledging_stamps_the_acknowledger(self):
        """An Acknowledged report must name who acknowledged it and when."""
        record = _new_report("_T-Employee-00003")

        record.status = "Acknowledged"
        record.save()

        self.assertEqual(record.acknowledged_by, frappe.session.user)
        self.assertIsNotNone(record.acknowledged_on)

        # Resolved so this employee's guard is clear for the next case.
        record.status = "Resolved"
        record.resolution_notes = "Deployed after acknowledgement"
        record.save()

    def test_resolving_requires_notes_and_stamps_the_resolver(self):
        """A Resolved report naming nobody as its resolver, or none, cannot be defended."""
        record = _new_report("_T-Employee-00003")

        record.status = "Resolved"
        with self.assertRaisesRegex(frappe.ValidationError, "Resolution Notes are required"):
            record.save()

        record.reload()
        record.status = "Resolved"
        record.resolution_notes = "Checked out of the building"
        record.save()

        self.assertEqual(record.resolved_by, frappe.session.user)
        self.assertIsNotNone(record.resolved_on)
