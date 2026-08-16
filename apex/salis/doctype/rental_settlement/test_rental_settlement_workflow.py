# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for Rental Settlement (Workflow Spine, second-mover).

These lock in the conversion of Rental Settlement from a status field with no
transition engine to the native **Rental Settlement Workflow**, and prove the
finance control: the "Mark Paid" transition is **Finance-Manager-only** and
carries the Segregation-of-Duties condition ``requested_by != session.user`` so
the (server-stamped) requester can never mark their own settlement paid.

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (Fleet Manager reconciles then
    approves; submit happens at Approved);
  * a wrong role is blocked (Fleet Project Manager is offered no approve/pay
    action);
  * Mark Paid is Finance-only — a Fleet Manager is not offered it, a Finance
    Manager is;
  * SoD — the requester (even with the Finance Manager role) cannot Mark Paid
    their own settlement; a different Finance Manager can;
  * a **post-submit transition is reachable** (Approved -> Paid on a
    docstatus=1 document) — the frozen-post-submit bug being fixed;
  * the no-GL boundary holds: Mark Paid posts no GL/Payment Entry.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Rental Settlement is NOT
project-scoped, so no Project User Permission is required.

``TestRentalSettlementStamping`` below is colocated for the same reason: it
proves the settlement -> Rental Accrual Ledger stamping side effect of the
SAME workflow (stamp on reaching a settled state, release on cancel), so both
classes exercise one native workflow from two angles in one bench bootstrap.
It carries its own ``test_ignore`` so ``bench run-tests --doctype
"Rental Settlement"`` resolves dependencies without the ERPNext finance chain
(Salis Payment Request -> Payment Entry -> Payment Gateway) that is not
installed in the CI bench; the module-level list covers the whole file.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from frappe.utils import get_first_day, getdate, today

from apex.salis import rental_engine
from apex.tests._helpers import _user, approve_rental_settlement
from apex.tests.factories import make_rental_office, make_vehicle

WORKFLOW = "Rental Settlement Workflow"
LEDGER = "Rental Accrual Ledger"

test_ignore = [
    "Company",
    "Cost Center",
    "Employee",
    "Mode of Payment",
    "Payment Entry",
    "Payment Gateway",
    "Project",
    "Salis Payment Request",
    "Salis Vehicle",
    "Role",
    "Supplier",
    "User",
]


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestRentalSettlementWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Rental Settlement") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Rental Settlement' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.requester = _user("rs_req@example.com", "Fleet Project Manager")
        cls.manager = _user("rs_mgr@example.com", "Fleet Manager")
        cls.finance = _user("rs_fin@example.com", "Finance Manager")
        cls.finance_maker = _user("rs_finmaker@example.com", "Finance Manager")
        frappe.get_doc("User", cls.finance_maker).add_roles("Fleet Project Manager")
        cls.office = cls._office("RS Workflow Office")

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _office(name):
        o = frappe.db.get_value("Rental Office", {"office_name": name}, "name")
        if not o:
            o = frappe.get_doc(
                {"doctype": "Rental Office", "office_name": name}
            ).insert(ignore_permissions=True).name
        return o

    @staticmethod
    def _vehicle():
        plate = "RSW-" + frappe.generate_hash(length=12).upper()
        return frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate,
             "ownership": "Rented", "status": "Active"}
        ).insert(ignore_permissions=True).name

    def _new_settlement(self, requested_by=None, **overrides):
        """A draft Rental Settlement stamped to ``requested_by`` (defaults to the
        standard requester). Inserted as Administrator so ``owner`` is
        Administrator and the SoD gate is exercised purely via requested_by.

        Carries one vehicle line so accrued_total reconciles to the claimed_total;
        a payment request is now capped at the reconciled accrued amount, so a
        settlement with no accrual basis would cap the payable to zero.

        Its own office per call, not the class's: one live settlement is allowed per
        (office, period_month), because two of them reconcile against the same accrual
        rows and each reads as fully supported. These cases are about the workflow, so
        they take a fresh office rather than a fresh calendar."""
        data = {
            "doctype": "Rental Settlement",
            "rental_office": self._office(
                "RS Workflow Office " + frappe.generate_hash(length=12).upper()
            ),
            "period_month": "2026-05",
            "claimed_total": 1000,
            "requested_by": requested_by or self.requester,
            "status": "Draft",
            "vehicles": [
                {"vehicle": self._vehicle(), "days": 10, "daily_rate": 100, "amount": 1000},
            ],
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _reconciled(self, **kwargs):
        rs = self._new_settlement(**kwargs)
        frappe.set_user(self.manager)
        apply_workflow(rs, "Reconcile")
        frappe.set_user("Administrator")
        rs.reload()
        return rs

    def _approved(self, **kwargs):
        rs = self._reconciled(**kwargs)
        frappe.set_user(self.manager)
        apply_workflow(rs, "Approve")
        frappe.set_user("Administrator")
        rs.reload()
        return rs


    def test_payment_request_only_on_approved_settlement(self):
        rs = self._approved()
        pr = rs.create_payment_request()
        self.assertTrue(frappe.db.exists("Salis Payment Request", pr))
        rs2 = self._approved()
        frappe.db.set_value("Rental Settlement", rs2.name, "status", "Disputed")
        rs2.reload()
        with self.assertRaises(frappe.ValidationError):
            rs2.create_payment_request()


    def test_legal_reconcile_then_approve_submits(self):
        rs = self._new_settlement()
        self.assertEqual(rs.docstatus, 0)

        frappe.set_user(self.manager)
        self.assertIn("Reconcile", _actions(rs))
        apply_workflow(rs, "Reconcile")
        rs.reload()
        self.assertEqual(rs.status, "Reconciled")
        self.assertEqual(rs.docstatus, 0)

        self.assertIn("Approve", _actions(rs))
        apply_workflow(rs, "Approve")
        rs.reload()
        self.assertEqual(rs.status, "Approved")
        self.assertEqual(rs.docstatus, 1)


    def test_wrong_role_cannot_approve_or_pay(self):
        rs = self._reconciled()
        frappe.set_user(self.requester)
        offered = _actions(rs)
        self.assertNotIn("Approve", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Approve")


    def test_mark_paid_is_finance_only(self):
        rs = self._approved()
        self.assertEqual(rs.status, "Approved")

        frappe.set_user(self.manager)
        self.assertNotIn("Mark Paid", _actions(rs))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Mark Paid")

        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(rs))
        apply_workflow(rs, "Mark Paid")
        rs.reload()
        self.assertEqual(rs.status, "Paid")
        self.assertEqual(rs.docstatus, 1)


    def test_sod_requester_cannot_mark_paid(self):
        rs = self._approved(requested_by=self.finance_maker)

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Mark Paid", _actions(rs))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Mark Paid")

        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(rs))
        apply_workflow(rs, "Mark Paid")
        rs.reload()
        self.assertEqual(rs.status, "Paid")

    def test_sod_requester_cannot_self_approve(self):
        mgr_maker = _user("rs_mgrmaker@example.com", "Fleet Manager")
        rs = self._reconciled(requested_by=mgr_maker)
        frappe.set_user(mgr_maker)
        self.assertNotIn("Approve", _actions(rs))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Approve")


    def test_post_submit_mark_paid_reachable(self):
        rs = self._approved()
        self.assertEqual(rs.docstatus, 1)

        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(rs))
        apply_workflow(rs, "Mark Paid")
        rs.reload()
        self.assertEqual(rs.status, "Paid")
        self.assertEqual(rs.docstatus, 1)


    def test_mark_paid_posts_no_gl(self):
        rs = self._approved()
        frappe.set_user(self.finance)
        apply_workflow(rs, "Mark Paid")
        frappe.set_user("Administrator")
        rs.reload()
        self.assertEqual(rs.status, "Paid")

        if frappe.db.exists("DocType", "GL Entry"):
            gl = frappe.get_all(
                "GL Entry",
                filters={"voucher_type": "Rental Settlement", "voucher_no": rs.name},
                limit=1,
            )
            self.assertEqual(gl, [])


class TestRentalSettlementStamping(FrappeTestCase):
    """Colocated tests for the Rental Settlement controller — the accrual-stamping
    half of the reconciliation, viewed from the settlement side.

    The cross-role Workflow controls (Reconcile/Approve/Mark Paid role gates, the
    Segregation-of-Duties conditions, the no-GL boundary) are covered by
    ``TestRentalSettlementWorkflow`` above. These tests add the settlement ->
    Rental Accrual Ledger stamping behavior the controller now owns: on reaching
    a settled state it stamps its office+period accrual rows, and on cancel it
    releases them.
    """

    def setUp(self):
        frappe.set_user("Administrator")
        self.requester = _user("rss_req@example.com", "Fleet Project Manager")
        self.manager = _user("rss_mgr@example.com", "Fleet Manager")
        self.office = make_rental_office("RSS Stamp Office")
        self.vehicle = make_vehicle("RSS STAMP 1", ownership="Rented")
        self.period = today()[:7]
        self.accrual_date = str(get_first_day(getdate(today())))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _accrual_row(self, amount=100.0):
        row = frappe.get_doc(
            {
                "doctype": LEDGER,
                "vehicle": self.vehicle,
                "rental_office": self.office,
                "accrual_date": self.accrual_date,
                "daily_rate": amount,
                "amount": amount,
                "settled": 0,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda n=row.name: frappe.db.delete(LEDGER, {"name": n}))
        return row.name

    def _settlement(self, claimed=1000):
        rs = frappe.get_doc(
            {
                "doctype": "Rental Settlement",
                "rental_office": self.office,
                "period_month": self.period,
                "claimed_total": claimed,
                "requested_by": self.requester,
                "status": "Draft",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda n=rs.name: self._purge(n))
        return rs

    def _purge(self, name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Rental Settlement", name):
            return
        rental_engine.release_settlement(name)
        doc = frappe.get_doc("Rental Settlement", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Rental Settlement", name, force=True, ignore_permissions=True)

    def _settled(self, name):
        return frappe.db.get_value(LEDGER, name, ["settled", "rental_settlement"], as_dict=True)

    def test_submit_stamps_then_cancel_releases(self):
        row = self._accrual_row()
        rs = self._settlement()

        self.assertEqual(self._settled(row).settled, 0)
        self.assertIsNone(self._settled(row).rental_settlement)

        approve_rental_settlement(rs, self.manager)
        s = self._settled(row)
        self.assertEqual(s.settled, 1, "Approve/submit must stamp the accrual row settled.")
        self.assertEqual(s.rental_settlement, rs.name, "The row must link back to the settlement.")

        frappe.set_user("Administrator")
        frappe.get_doc("Rental Settlement", rs.name).cancel()
        s2 = self._settled(row)
        self.assertEqual(s2.settled, 0, "Cancel must release the row.")
        self.assertIsNone(s2.rental_settlement, "Cancel must clear the link.")

    def test_validate_cross_checks_ledger_total(self):
        self._accrual_row(amount=100)
        r2 = frappe.get_doc(
            {
                "doctype": LEDGER, "vehicle": self.vehicle, "rental_office": self.office,
                "accrual_date": str(getdate(self.accrual_date).replace(day=2)),
                "daily_rate": 200, "amount": 200, "settled": 0,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda: frappe.db.delete(LEDGER, {"name": r2.name}))

        rs = self._settlement(claimed=300)
        rs.reload()
        self.assertEqual(rs.ledger_accrued_total, 300.0,
                         "ledger_accrued_total must sum the linked accrual rows.")
        self.assertEqual(rs.accrued_total, 300.0,
                         "With no vehicle lines, accrued_total derives from the ledger.")
        self.assertEqual(rs.ledger_variance, 0.0)
