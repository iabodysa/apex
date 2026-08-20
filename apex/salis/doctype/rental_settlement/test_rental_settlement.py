# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.rental_settlement.rental_settlement import RentalSettlement
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from frappe.utils import get_first_day, getdate, today
from apex.salis import rental_engine
from apex.tests._helpers import _user, approve_rental_settlement
from apex.tests.factories import make_rental_office, make_vehicle



class TestRentalSettlement(FrappeTestCase):
    def test_draft_line_amount_is_derived_from_days_and_rate(self):
        settlement = RentalSettlement(
            {
                "doctype": "Rental Settlement",
                "docstatus": 0,
                "status": "Draft",
                "requested_by": "Administrator",
                "company": "Apex Co",
                "rental_office": "Rental Office A",
                "period_month": "2026-08",
                "claimed_total": 200,
                "vehicles": [
                    {
                        "doctype": "Rental Settlement Item",
                        "vehicle": "VEH-1",
                        "days": 2,
                        "daily_rate": 100,
                    }
                ],
            }
        )

        with (
            patch("apex.salis.rental_engine.linked_accrued_total", return_value=200),
            patch("apex.salis.doctype.rental_settlement.rental_settlement.apply_vat"),
        ):
            settlement.validate()

        self.assertEqual(settlement.vehicles[0].amount, 200)
        self.assertEqual(settlement.accrued_total, 200)

    def test_submitted_line_keeps_its_historical_amount(self):
        settlement = RentalSettlement(
            {
                "doctype": "Rental Settlement",
                "docstatus": 1,
                "status": "Approved",
                "requested_by": "Administrator",
                "company": "Apex Co",
                "rental_office": "Rental Office A",
                "period_month": "2026-08",
                "claimed_total": 175,
                "vehicles": [
                    {
                        "doctype": "Rental Settlement Item",
                        "vehicle": "VEH-1",
                        "days": 2,
                        "daily_rate": 100,
                        "amount": 175,
                    }
                ],
            }
        )

        with (
            patch("apex.salis.rental_engine.linked_accrued_total", return_value=175),
            patch("apex.salis.doctype.rental_settlement.rental_settlement.apply_vat"),
        ):
            settlement.validate()

        self.assertEqual(settlement.vehicles[0].amount, 175)


class TestATypedZeroSurvives(FrappeTestCase):
    """A settlement line typed as zero and a line left blank are two different facts.

    ``validate`` must overwrite a draft line's amount only when ``_amount_was_derived``
    says it is ours to recompute (rental_settlement.py:149-164), not every draft line
    unconditionally: a row of days=3, daily_rate=100, amount=0 must save as 0, not the
    recomputed 300. Overwriting an explicit zero would make a settlement claiming nothing
    report a perfect match against the rental accrual ledger, since ``accrued_total`` would
    then read the recomputed 300 rather than the 0 the operator typed.

    The distinction was measured before it was relied on. A Currency child column is NOT NULL
    DEFAULT 0, so the stored row cannot carry it; only the incoming request can, where an
    omitted field arrives as None and a typed 0 arrives as 0.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.office = (
            frappe.get_doc(
                {
                    "doctype": "Rental Office",
                    "office_name": "_ZS " + frappe.generate_hash(length=12).upper(),
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls.addClassCleanup(
            frappe.delete_doc, "Rental Office", cls.office, force=True, ignore_permissions=True
        )
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "_T ABC 1001"}, "name")

    def _settlement(self, rows, period_month="2026-05"):
        doc = frappe.get_doc(
            {
                "doctype": "Rental Settlement",
                "rental_office": self.office,
                "period_month": period_month,
                "claimed_total": 0,
            }
        )
        for row in rows:
            doc.append("vehicles", {"vehicle": self.vehicle, **row})
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Rental Settlement", doc.name, force=True, ignore_permissions=True
        )
        return doc

    def test_a_typed_zero_amount_is_not_recomputed(self):
        """The operator said this vehicle owes nothing. Days x rate must not overrule."""
        doc = self._settlement([{"days": 3, "daily_rate": 100, "amount": 0}])
        doc.reload()
        self.assertEqual(
            doc.vehicles[0].amount,
            0,
            "a typed 0 was overwritten with days x daily_rate",
        )

    def test_a_blank_amount_is_still_computed(self):
        """The other half: absence must keep its convenience."""
        doc = self._settlement([{"days": 3, "daily_rate": 100}])
        doc.reload()
        self.assertEqual(doc.vehicles[0].amount, 300)

    def test_a_settlement_totalling_zero_keeps_zero_and_does_not_match_the_ledger(self):
        """The defect that mattered: nothing claimed must not read as a perfect match."""
        doc = self._settlement([{"days": 3, "daily_rate": 100, "amount": 0}])
        doc.reload()
        self.assertEqual(doc.accrued_total, 0, "the settlement's own total was replaced")
        self.assertFalse(
            doc.accrued_from_ledger,
            "the ledger was substituted for a settlement that HAS rows",
        )
        self.assertEqual(
            doc.ledger_variance,
            -doc.ledger_accrued_total,
            "variance against the ledger must show the full gap, not 0",
        )

    def test_a_settlement_with_no_rows_still_falls_back_and_says_so(self):
        """The fallback is kept for the one case it was meant for, and recorded."""
        doc = self._settlement([])
        doc.reload()
        self.assertEqual(doc.accrued_total, doc.ledger_accrued_total)
        self.assertTrue(
            doc.accrued_from_ledger,
            "the substitution happened but the document does not say so",
        )

    def test_a_derived_amount_still_follows_an_edit_to_its_inputs(self):
        """The convenience the read-only field depends on survives the new rule."""
        doc = self._settlement([{"days": 3, "daily_rate": 100}])
        doc.reload()
        doc.vehicles[0].days = 5
        doc.save(ignore_permissions=True)
        doc.reload()
        self.assertEqual(doc.vehicles[0].amount, 500, "a derived line went stale after an edit")

    def test_two_settlements_cannot_claim_one_office_month(self):
        """The other way this reconciliation reads as supported when it is not: both
        settlements cross-check against the SAME unsettled accrual rows, so each reports
        a perfect match and the office is paid twice for one month."""
        self._settlement([{"days": 3, "daily_rate": 100}])

        with self.assertRaises(frappe.ValidationError):
            self._settlement([{"days": 3, "daily_rate": 100}])

    def test_a_second_settlement_for_another_month_is_allowed(self):
        """The guard is (office, period), not office."""
        self._settlement([{"days": 3, "daily_rate": 100}])
        other = self._settlement([{"days": 3, "daily_rate": 100}], period_month="2026-06")

        self.assertTrue(other.name)

    def test_a_typed_zero_survives_an_edit_to_its_inputs(self):
        """And the override survives the same round trip that re-derives its neighbour."""
        doc = self._settlement([{"days": 3, "daily_rate": 100, "amount": 0}])
        doc.reload()
        doc.vehicles[0].days = 5
        doc.save(ignore_permissions=True)
        doc.reload()
        self.assertEqual(doc.vehicles[0].amount, 0, "the operator's 0 was recomputed on re-save")

test_dependencies = ['Salis Vehicle']
test_ignore = ['Company', 'Cost Center', 'Employee', 'Mode of Payment', 'Payment Entry', 'Payment Gateway', 'Project', 'Salis Payment Request', 'Salis Vehicle', 'Role', 'Supplier', 'User']


# --- merged from test_rental_settlement_workflow.py ---
WORKFLOW = "Rental Settlement Workflow"
LEDGER = "Rental Accrual Ledger"
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
