# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests import factories

test_ignore = [
    "Company",
    "Supplier",
    "Currency",
    "Cost Center",
    "Project",
    "Item",
    "Employee",
    "Department",
]


class TestSIMCustodyAssignment(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.cost_center = frappe.db.get_value("Company", cls.company, "cost_center")
        cls.employee = factories.make_employee("Custody Holder One", company=cls.company).name
        if cls.cost_center:
            frappe.db.set_value("Employee", cls.employee, "payroll_cost_center", cls.cost_center)
        cls.contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": cls.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        cls.contract.insert(ignore_permissions=True, ignore_links=True)

    def tearDown(self):
        frappe.db.rollback()

    def _sim(self, mobile="0551000001"):
        return frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.company,
                "telecom_contract": self.contract.name,
                "mobile_number": mobile,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def _event(self, sim, action, **kw):
        doc = frappe.get_doc(
            {
                "doctype": "SIM Custody Assignment",
                "naming_series": "SIM-CUST-.YYYY.-.#####",
                "company": self.company,
                "sim_card": sim.name,
                "action": action,
                "assignment_date": kw.pop("assignment_date", "2026-06-01"),
                **kw,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def _status(self, sim):
        return frappe.db.get_value("SIM Card", sim.name, "status")

    def test_assign_projects_state_and_snapshots_cost_center(self):
        sim = self._sim()
        event = self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self.assertEqual(self._status(sim), "Assigned")
        projection = frappe.db.get_value(
            "SIM Card",
            sim.name,
            ["current_custodian_employee", "current_assignment", "current_cost_center"],
            as_dict=True,
        )
        self.assertEqual(projection.current_custodian_employee, self.employee)
        self.assertEqual(projection.current_assignment, event.name)
        # Cost center resolved from the employee and frozen on the event.
        self.assertEqual(event.cost_center, self.cost_center)
        self.assertEqual(projection.current_cost_center, self.cost_center)

    def test_only_one_active_custody(self):
        sim = self._sim()
        self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        with self.assertRaises(frappe.ValidationError):
            self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)

    def test_suspended_sim_cannot_be_assigned(self):
        sim = self._sim()
        self._event(sim, "Suspend")
        self.assertEqual(self._status(sim), "Suspended")
        with self.assertRaises(frappe.ValidationError):
            self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)

    def test_transfer_return_reactivate_cycle(self):
        sim = self._sim()
        self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        project = factories.make_project("SIM Custody Project")
        self._event(sim, "Transfer", custodian_type="Project", project=project)
        self.assertEqual(self._status(sim), "Assigned")
        self.assertEqual(
            frappe.db.get_value("SIM Card", sim.name, "current_project"), project
        )
        self._event(sim, "Return")
        self.assertEqual(self._status(sim), "Available")
        self.assertIsNone(frappe.db.get_value("SIM Card", sim.name, "current_custodian_employee"))
        # Suspend an Available SIM, then Reactivate back to Available.
        self._event(sim, "Suspend")
        self._event(sim, "Reactivate")
        self.assertEqual(self._status(sim), "Available")

    def test_incompatible_company_fails_closed(self):
        sim = self._sim()
        other_company = factories.make_company("Other AFMCO", abbr="OAFM").name
        other_employee = factories.make_employee("Foreign Holder", company=other_company).name
        with self.assertRaises(frappe.ValidationError):
            self._event(sim, "Assign", custodian_type="Employee", employee=other_employee)

    def test_the_replay_reads_the_event_chain_for_update(self):
        """The SIM row lock does not refresh the reader's snapshot; the replay must.

        ``on_submit`` locks the SIM row, but ``validate`` already pinned this
        transaction's REPEATABLE READ view with a plain read of that same row. A
        non-locking replay therefore answers from the pre-lock snapshot and folds an
        event set that is missing the winner's just-committed event, writing the wrong
        custodian onto the SIM. Calls the PRODUCTION function and captures the SQL it
        emits, the same way the fuel-quota lock is graded.
        """
        from apex.logistay.doctype.sim_custody_assignment.sim_custody_assignment import (
            rebuild_sim_projection,
        )

        captured: list[str] = []
        real_sql = frappe.db.sql

        def _recording_sql(query, *args, **kwargs):
            captured.append(str(query))
            return real_sql(query, *args, **kwargs)

        frappe.db.sql = _recording_sql
        try:
            rebuild_sim_projection(f"NO-SUCH-SIM-{frappe.generate_hash(length=12)}")
        finally:
            frappe.db.sql = real_sql

        locking = [
            q for q in captured
            if "SIM Custody Assignment" in q and "FOR UPDATE" in q.upper()
        ]
        self.assertTrue(
            locking,
            "rebuild_sim_projection must read the event chain with FOR UPDATE, or the "
            f"loser of the SIM lock replays a stale snapshot. Captured: {captured}",
        )

    def test_back_dated_return_is_refused_like_a_back_dated_retirement(self):
        """The replay orders by date, so ANY back-dated event is silently overwritten.

        Named to sort AFTER ``test_assign_...``: this class shares state built in
        ``setUpClass`` while its ``tearDown`` issues a full ``frappe.db.rollback()``, so
        the first method to run takes that shared state down with it.

        The guard used to run for Lost/Terminated only, which left a back-dated Return,
        Suspend or Transfer to submit successfully and change nothing — the operator gets
        a submitted event and a SIM whose custody never moved.
        """
        sim = self._sim(mobile="0551000042")
        self._event(
            sim, "Assign", custodian_type="Employee", employee=self.employee,
            assignment_date="2026-06-01",
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            self._event(sim, "Return", assignment_date="2026-05-01")
        self.assertIn("2026-05-01", str(caught.exception))
        self.assertEqual(
            self._status(sim), "Assigned",
            "the refused Return must leave the projection exactly where it was",
        )

    def test_projection_matches_latest_after_cancel(self):
        sim = self._sim()
        first = self._event(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self._event(sim, "Return")
        self.assertEqual(self._status(sim), "Available")
        # Cancelling the Return rolls the SIM back to the Assigned state it had.
        returns = frappe.get_all(
            "SIM Custody Assignment",
            filters={"sim_card": sim.name, "action": "Return", "docstatus": 1},
            pluck="name",
        )
        frappe.get_doc("SIM Custody Assignment", returns[0]).cancel()
        self.assertEqual(self._status(sim), "Assigned")
        self.assertEqual(
            frappe.db.get_value("SIM Card", sim.name, "current_assignment"), first.name
        )
