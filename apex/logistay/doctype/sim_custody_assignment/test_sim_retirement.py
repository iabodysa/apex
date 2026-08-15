# Copyright (c) 2026, AFMCO and contributors
"""Retiring a SIM as Lost or Terminated.

Retirement is an EVENT in the custody chain, not a status edit, so the proofs here
are about the chain: the terminal event closes the active custody, the SIM and its
history survive, the terminal state absorbs, and cancelling the event puts the SIM
back exactly where it was. The last one is why the projection may not "preserve" a
terminal status it reads off the row it is about to overwrite — that shortcut makes
a Lost SIM unrecoverable, so a test has to hold it down.

Every SIM here is minted PER TEST METHOD with its own mobile number: FrappeTestCase
rolls back once per class, so two methods sharing a fixture row share its mutations.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.api import sim_actions
from apex.tests import factories
from apex.tests._helpers import _user

REASON = "Handset stolen on site; police report filed."

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


class _RetirementCase(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = factories.make_company("Test AFMCO").name
        cls.employee = factories.make_employee("Retirement Holder", company=cls.company).name
        factories.make_supplier("QA-TELECOM-SUPPLIER")
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
        cls.contract.submit()

    def setUp(self):
        # frappe.session.user is a process global and does NOT roll back; restore it
        # before anything can change it, so a failure mid-test cannot leak the
        # identity into the next test in this process.
        self.addCleanup(frappe.set_user, "Administrator")
        self._seq = 0
        frappe.db.savepoint("sim_retirement")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="sim_retirement")

    def sim(self):
        """A fresh Available SIM with a mobile number unique to this method."""
        self._seq += 1
        mobile = f"0559{abs(hash(self.id())) % 100000:05d}{self._seq}"
        return frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.company,
                "telecom_contract": self.contract.name,
                "mobile_number": mobile,
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    @staticmethod
    def act(sim, action, **kw):
        return sim_actions.perform_custody_action(sim.name, action, **kw)

    @staticmethod
    def status(sim):
        return frappe.db.get_value("SIM Card", sim.name, "status")

    @staticmethod
    def events(sim):
        """How many submitted custody events this SIM carries. Counted, never
        merely observed: 'a row exists' is equally true of a double post."""
        return frappe.db.count("SIM Custody Assignment", {"sim_card": sim.name, "docstatus": 1})


class TestRetirementClosesCustodyWithoutDeleting(_RetirementCase):
    def test_lost_from_assigned_closes_custody_and_keeps_the_sim(self):
        sim = self.sim()
        self.act(sim, "Assign", custodian_type="Employee", employee=self.employee)
        result = self.act(sim, "Lost", reason=REASON)

        self.assertEqual(result["status"], "Lost")
        projection = frappe.db.get_value(
            "SIM Card",
            sim.name,
            ["status", "current_custodian_type", "current_custodian_employee", "current_assignment"],
            as_dict=True,
        )
        self.assertEqual(projection.status, "Lost")
        # Custody is CLOSED, not left dangling on a SIM nobody can hand back.
        self.assertEqual(projection.current_custodian_type, "Unassigned")
        self.assertIsNone(projection.current_custodian_employee)
        self.assertIsNone(projection.current_assignment)
        # Nothing was deleted: the SIM row and both events survive.
        self.assertTrue(frappe.db.exists("SIM Card", sim.name))
        self.assertEqual(self.events(sim), 2)

    def test_the_retirement_event_records_who_held_the_sim(self):
        """History remains queryable — the custodian is cleared from the projection
        but preserved on the event, which is the whole point of not deleting."""
        sim = self.sim()
        self.act(sim, "Assign", custodian_type="Employee", employee=self.employee)
        retirement = self.act(sim, "Lost", reason=REASON)

        event = frappe.get_doc("SIM Custody Assignment", retirement["assignment"])
        self.assertEqual(event.action, "Lost")
        self.assertEqual(event.previous_custodian_employee, self.employee)
        self.assertEqual(event.previous_custodian_type, "Employee")
        self.assertEqual(event.reason, REASON)
        self.assertEqual(event.docstatus, 1)

        history = frappe.get_all(
            "SIM Custody Assignment",
            filters={"sim_card": sim.name, "docstatus": 1},
            pluck="action",
        )
        self.assertCountEqual(history, ["Assign", "Lost"])

    def test_terminate_an_available_sim_needs_no_custodian(self):
        sim = self.sim()
        result = self.act(sim, "Terminated", reason="Contract closed; SIM returned to carrier.")
        self.assertEqual(result["status"], "Terminated")
        self.assertEqual(self.events(sim), 1)

    def test_retiring_twice_is_refused_not_double_posted(self):
        sim = self.sim()
        self.act(sim, "Lost", reason=REASON)
        with self.assertRaises(frappe.ValidationError) as caught:
            self.act(sim, "Lost", reason=REASON)
        self.assertIn("expected", str(caught.exception))
        # The refusal left no second event behind.
        self.assertEqual(self.events(sim), 1)


class TestRetirementDemandsAReason(_RetirementCase):
    """``mandatory_depends_on`` on the Reason field is a CLIENT-side hint only —
    Frappe's mandatory check filters on ``reqd`` alone
    (frappe/model/base_document.py:775) — so without the controller guard an API
    call retires a SIM with no reason recorded at all."""

    def _assert_reason_demanded(self, action):
        sim = self.sim()
        with self.assertRaises(frappe.ValidationError) as caught:
            self.act(sim, action, reason=None)
        # Assert the MESSAGE, not the type: a link check or a mandatory-field error
        # raises the same ValidationError and would satisfy a bare assertRaises.
        message = str(caught.exception)
        self.assertIn("Reason", message)
        self.assertIn(sim.name, message)
        # Refused means nothing persisted and the SIM never moved.
        self.assertEqual(self.events(sim), 0)
        self.assertEqual(self.status(sim), "Available")

    def test_lost_without_a_reason_is_refused(self):
        self._assert_reason_demanded("Lost")

    def test_terminated_without_a_reason_is_refused(self):
        self._assert_reason_demanded("Terminated")

    def test_a_whitespace_only_reason_is_not_a_reason(self):
        sim = self.sim()
        with self.assertRaises(frappe.ValidationError) as caught:
            self.act(sim, "Lost", reason="   \n  ")
        self.assertIn("Reason", str(caught.exception))
        self.assertEqual(self.events(sim), 0)

    def test_a_non_terminal_action_still_needs_no_reason(self):
        """The guard must not spread: Suspend never required a reason."""
        sim = self.sim()
        self.act(sim, "Suspend")
        self.assertEqual(self.status(sim), "Suspended")


class TestTerminalStatesAbsorb(_RetirementCase):
    def test_nothing_may_follow_a_terminated_sim(self):
        sim = self.sim()
        self.act(sim, "Terminated", reason="Contract closed.")
        for action in ("Assign", "Transfer", "Return", "Suspend", "Reactivate", "Lost", "Terminated"):
            with self.subTest(action=action):
                with self.assertRaises(frappe.ValidationError) as caught:
                    self.act(
                        sim,
                        action,
                        custodian_type="Employee",
                        employee=self.employee,
                        reason=REASON,
                    )
                self.assertIn("expected", str(caught.exception))
        self.assertEqual(self.events(sim), 1)
        self.assertEqual(self.status(sim), "Terminated")

    def test_a_lost_sim_cannot_be_reassigned(self):
        sim = self.sim()
        self.act(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self.act(sim, "Lost", reason=REASON)
        with self.assertRaises(frappe.ValidationError) as caught:
            self.act(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self.assertIn("expected", str(caught.exception))
        self.assertEqual(self.status(sim), "Lost")

    def test_a_lost_sim_may_still_be_terminated(self):
        """The one transition out of Lost: the carrier closes the line afterwards."""
        sim = self.sim()
        self.act(sim, "Lost", reason=REASON)
        self.act(sim, "Terminated", reason="Line closed with the carrier after loss.")
        self.assertEqual(self.status(sim), "Terminated")
        self.assertEqual(self.events(sim), 2)

    def test_a_suspended_sim_may_be_retired(self):
        sim = self.sim()
        self.act(sim, "Suspend")
        self.act(sim, "Lost", reason=REASON)
        self.assertEqual(self.status(sim), "Lost")

    def test_a_back_dated_retirement_is_refused(self):
        """The replay is ordered by assignment_date, so a Lost dated BEFORE the Assign
        replays first and the Assign overwrites it — the operator retires the SIM and
        the SIM still reads Assigned. The submit-time status check cannot see this: it
        reads the current status, which legitimately permits the transition."""
        sim = self.sim()
        self.act(
            sim,
            "Assign",
            custodian_type="Employee",
            employee=self.employee,
            assignment_date="2026-06-01",
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            self.act(sim, "Lost", reason=REASON, assignment_date="2026-05-01")
        message = str(caught.exception)
        self.assertIn("2026-05-01", message)
        self.assertIn("2026-06-01", message)
        self.assertEqual(self.events(sim), 1)
        self.assertEqual(self.status(sim), "Assigned")

    def test_a_same_day_retirement_is_accepted(self):
        """The guard rejects EARLIER, not equal: retiring a SIM assigned today is the
        normal case, and creation order breaks the tie in the replay."""
        sim = self.sim()
        self.act(
            sim,
            "Assign",
            custodian_type="Employee",
            employee=self.employee,
            assignment_date="2026-06-01",
        )
        self.act(sim, "Lost", reason=REASON, assignment_date="2026-06-01")
        self.assertEqual(self.status(sim), "Lost")

    def test_an_unknown_action_is_still_rejected(self):
        sim = self.sim()
        with self.assertRaises(frappe.ValidationError) as caught:
            self.act(sim, "Vaporise", reason=REASON)
        self.assertIn("Vaporise", str(caught.exception))


class TestRetirementIsReversible(_RetirementCase):
    def test_cancelling_the_lost_event_restores_the_prior_custody(self):
        """Without this, retirement is a one-way door: a projection that re-reads the
        terminal status off the SIM row it is overwriting pins the SIM at Lost
        forever, and the only remaining fix is deleting the record."""
        sim = self.sim()
        assign = self.act(sim, "Assign", custodian_type="Employee", employee=self.employee)
        retirement = self.act(sim, "Lost", reason=REASON)
        self.assertEqual(self.status(sim), "Lost")

        frappe.get_doc("SIM Custody Assignment", retirement["assignment"]).cancel()

        projection = frappe.db.get_value(
            "SIM Card",
            sim.name,
            ["status", "current_custodian_employee", "current_assignment"],
            as_dict=True,
        )
        self.assertEqual(projection.status, "Assigned")
        self.assertEqual(projection.current_custodian_employee, self.employee)
        self.assertEqual(projection.current_assignment, assign["assignment"])
        # The cancelled event is retained as a cancelled document, not removed.
        self.assertTrue(frappe.db.exists("SIM Custody Assignment", retirement["assignment"]))
        self.assertEqual(self.events(sim), 1)

    def test_cancelling_a_termination_returns_an_available_sim_to_available(self):
        sim = self.sim()
        retirement = self.act(sim, "Terminated", reason="Raised in error.")
        frappe.get_doc("SIM Custody Assignment", retirement["assignment"]).cancel()
        self.assertEqual(self.status(sim), "Available")
        self.assertEqual(self.events(sim), 0)

    def test_a_reinstated_sim_can_be_assigned_again(self):
        sim = self.sim()
        retirement = self.act(sim, "Lost", reason=REASON)
        frappe.get_doc("SIM Custody Assignment", retirement["assignment"]).cancel()
        self.act(sim, "Assign", custodian_type="Employee", employee=self.employee)
        self.assertEqual(self.status(sim), "Assigned")


class TestARealOperatorCanRetireASim(_RetirementCase):
    """The DocPerm reachability proof. Every other test in this file inserts as
    Administrator, which proves nothing about whether the role that actually does
    this work can: an omitted DocPerm flag ships as 0, not as its default."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = _user("sim_retire_op@example.com", "SIM Operations User")
        cls.outsider_company = factories.make_company("Other AFMCO", abbr="OAFM").name
        if not frappe.db.exists(
            "User Permission",
            {"allow": "Company", "for_value": cls.company, "user": cls.operator},
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "allow": "Company",
                    "for_value": cls.company,
                    "user": cls.operator,
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        # Restore the identity FIRST: frappe.session.user is a process global that no
        # rollback touches, and the class teardown below runs DB work of its own.
        frappe.set_user("Administrator")
        # Deliberately no db.commit() here — committing would also make this class's
        # SIM and contract rows permanent on the shared test site by emptying the
        # transaction FrappeTestCase.tearDownClass is about to roll back.
        frappe.db.delete(
            "User Permission",
            {"allow": "Company", "for_value": cls.company, "user": cls.operator},
        )
        super().tearDownClass()

    def test_a_sim_operations_user_can_retire_a_sim_in_their_own_company(self):
        sim = self.sim()
        frappe.set_user(self.operator)
        result = sim_actions.perform_custody_action(sim.name, "Lost", reason=REASON)
        self.assertEqual(result["status"], "Lost")
        # The event was authored by the operator, not silently by Administrator.
        self.assertEqual(
            frappe.db.get_value("SIM Custody Assignment", result["assignment"], "owner"),
            self.operator,
        )

    def test_retirement_needs_no_delete_right(self):
        """Retirement must be reachable by a role that cannot delete anything —
        that is the difference between closing a SIM and erasing it."""
        for doctype in ("SIM Card", "SIM Custody Assignment"):
            with self.subTest(doctype=doctype):
                self.assertFalse(
                    frappe.has_permission(doctype, "delete", user=self.operator),
                    f"{doctype}: SIM Operations User must not hold delete",
                )
        self.assertTrue(frappe.has_permission("SIM Custody Assignment", "create", user=self.operator))
        self.assertTrue(frappe.has_permission("SIM Custody Assignment", "submit", user=self.operator))

    def test_a_scoped_operator_cannot_retire_another_company_s_sim(self):
        foreign_supplier = factories.make_supplier("QA-TELECOM-SUPPLIER-FOREIGN")
        foreign_contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": self.outsider_company,
                "supplier": foreign_supplier,
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        foreign_contract.insert(ignore_permissions=True, ignore_links=True)
        foreign_contract.submit()
        foreign_sim = frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.outsider_company,
                "telecom_contract": foreign_contract.name,
                "mobile_number": "0558000777",
            }
        ).insert(ignore_permissions=True, ignore_links=True)

        frappe.set_user(self.operator)
        with self.assertRaises(frappe.PermissionError):
            sim_actions.perform_custody_action(foreign_sim.name, "Lost", reason=REASON)
        frappe.set_user("Administrator")
        self.assertEqual(self.status(foreign_sim), "Available")
        self.assertEqual(self.events(foreign_sim), 0)
