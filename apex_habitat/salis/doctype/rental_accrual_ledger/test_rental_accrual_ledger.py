"""Tests for the Rental Accrual Ledger <-> Rental Settlement reconciliation.

The rental accrual engine writes one machine-only Rental Accrual Ledger row per
in-service rented vehicle per day, always ``settled = 0`` with no settlement
link. The second half of the loop — never previously built — is the settlement
stamping these rows: when a Rental Settlement reaches a settled state (Approved
or Paid), the unsettled accrual rows for the SAME rental_office + period are
stamped ``rental_settlement = <settlement> / settled = 1``; cancelling the
settlement releases them.

These tests prove:
  * a submitted/approved settlement stamps its office+period accrual rows
    (settled = 1 + link set), and leaves another office's / another period's
    rows untouched;
  * the stamp is idempotent — Approve then Mark Paid (two post-submit saves)
    never double-stamp, and a second settlement for the same period finds
    nothing left to stamp (no double-stamp / no re-pointing);
  * cancelling the settlement releases the rows (settled = 0, link cleared);
  * the Rental Cost by Office report's Settled / Outstanding split reflects the
    stamped reality;
  * the controller cross-checks accrued_total against the linked ledger total
    (ledger_accrued_total / ledger_variance), and derives it when no vehicle
    lines are entered;
  * monthly_rental_reconciliation flags an office that still has unsettled rows
    for the closed period, and is idempotent.

The settlement is driven through the real Rental Settlement Workflow as the
concrete approver role (the same path a desk action takes), with a direct
submit fallback on a site where the workflow is not seeded.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, flt, get_first_day, getdate, today

from apex_habitat.salis import rental_engine
from apex_habitat.salis.report.rental_cost_by_office.rental_cost_by_office import (
    execute as rental_cost_by_office,
)
from apex_habitat.tests._helpers import _user

LEDGER = "Rental Accrual Ledger"

# Keep the Frappe runner from auto-building test records for Link-field deps that
# pull in ERPNext finance DocTypes not present in the CI bench. The new
# ``rental_settlement`` link on this ledger introduces a Rental Settlement ->
# Salis Payment Request -> Payment Entry -> Payment Gateway chain that the
# dependency walker would otherwise try to materialise (Payment Gateway is not
# installed). These tests build their own Rental Settlement / accrual rows
# explicitly, so the auto-record dependency on that whole subtree is pruned here
# (Rental Settlement at the top severs the chain). Mirrors the colocated fuel
# ledger test's test_ignore.
test_ignore = [
    "Company",
    "Cost Center",
    "Employee",
    "Mode of Payment",
    "Payment Entry",
    "Payment Gateway",
    "Project",
    "Rental Settlement",
    "Role",
    "Salis Payment Request",
    "Supplier",
    "User",
]


def _settled(name):
    return frappe.db.get_value(LEDGER, name, ["settled", "rental_settlement"], as_dict=True)


class TestRentalSettlementReconciliation(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Masters are (re)materialised per-test, not in setUpClass: FrappeTestCase
        # rolls the whole connection back after each test, which would wipe
        # uncommitted setUpClass inserts and leave later tests with dangling
        # Link targets. get-or-create here is rollback-safe and idempotent.
        self.requester = _user("ral_req@example.com", "Fleet Project Manager")
        self.manager = _user("ral_mgr@example.com", "Fleet Manager")
        self.finance = _user("ral_fin@example.com", "Finance Manager")
        self.office = self._office("RAL Recon Office")
        self.other_office = self._office("RAL Other Office")
        self.vehicle = self._vehicle("RAL RECON 1")
        # A fixed in-period day (first of the current month) so the period window
        # always contains the seeded accrual rows regardless of the run date.
        self.period = today()[:7]
        self.accrual_date = str(get_first_day(getdate(today())))

    def tearDown(self):
        frappe.set_user("Administrator")

    # --- builders ------------------------------------------------------------

    @staticmethod
    def _office(name):
        o = frappe.db.get_value("Rental Office", {"office_name": name}, "name")
        if not o:
            o = frappe.get_doc(
                {"doctype": "Rental Office", "office_name": name, "status": "Active"}
            ).insert(ignore_permissions=True).name
        return o

    @staticmethod
    def _vehicle(plate):
        v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not v:
            v = frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate,
                 "ownership": "Rented", "status": "Active"}
            ).insert(ignore_permissions=True).name
        return v

    def _accrual_row(self, office, accrual_date, amount=100.0, vehicle=None):
        """Insert a machine-style accrual row (settled = 0, unlinked), exactly as
        the engine writes it. Returns its name; auto-cleaned on tearDown.

        Each row gets its OWN vehicle by default so multiple rows on the same
        accrual_date do not collide on the ledger's UNIQUE (vehicle, accrual_date)
        index — the office+period selector under test keys on rental_office +
        accrual_date, never on the vehicle, so distinct vehicles are immaterial to
        what the stamping must match."""
        if vehicle is None:
            self._veh_counter = getattr(self, "_veh_counter", 0) + 1
            vehicle = self._vehicle(f"RAL RECON ROW {self._veh_counter}")
        row = frappe.get_doc(
            {
                "doctype": LEDGER,
                "vehicle": vehicle,
                "rental_office": office,
                "accrual_date": accrual_date,
                "daily_rate": amount,
                "amount": amount,
                "settled": 0,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda n=row.name: frappe.db.delete(LEDGER, {"name": n}))
        return row.name

    def _settlement(self, office=None, period=None, claimed=1000, vehicles=None):
        data = {
            "doctype": "Rental Settlement",
            "rental_office": office or self.office,
            "period_month": period or self.period,
            "claimed_total": claimed,
            "requested_by": self.requester,
            "status": "Draft",
        }
        if vehicles:
            data["vehicles"] = vehicles
        rs = frappe.get_doc(data).insert(ignore_permissions=True)
        self.addCleanup(lambda n=rs.name: self._purge_settlement(n))
        return rs

    def _purge_settlement(self, name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Rental Settlement", name):
            return
        # Release any rows still linked so the delete leaves no dangling link.
        rental_engine.release_settlement(name)
        doc = frappe.get_doc("Rental Settlement", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Rental Settlement", name, force=True, ignore_permissions=True)

    def _approve(self, rs):
        """Drive Draft -> Reconciled -> Approved (submits) via the workflow as the
        Fleet Manager, or fall back to a direct submit when the workflow is not
        seeded on this site."""
        from frappe.model.workflow import apply_workflow, get_workflow_name

        if get_workflow_name("Rental Settlement") == "Rental Settlement Workflow":
            frappe.set_user(self.manager)
            apply_workflow(rs, "Reconcile")
            rs.reload()
            apply_workflow(rs, "Approve")
            frappe.set_user("Administrator")
        else:
            rs.status = "Approved"
            rs.save(ignore_permissions=True)
            rs.submit()
        rs.reload()
        return rs

    def _mark_paid(self, rs):
        from frappe.model.workflow import apply_workflow, get_workflow_name

        if get_workflow_name("Rental Settlement") == "Rental Settlement Workflow":
            frappe.set_user(self.finance)
            apply_workflow(rs, "Mark Paid")
            frappe.set_user("Administrator")
        else:
            rs.status = "Paid"
            rs.save(ignore_permissions=True)
        rs.reload()
        return rs

    # --- stamp on approve ----------------------------------------------------

    def test_approve_stamps_office_period_rows_only(self):
        # Two rows in the target office+period, one in another office, one in the
        # previous period — only the first two should be stamped.
        in1 = self._accrual_row(self.office, self.accrual_date)
        in2 = self._accrual_row(self.office, self.accrual_date, amount=150)
        other_office = self._accrual_row(self.other_office, self.accrual_date)
        prev_period = self._accrual_row(
            self.office, str(get_first_day(add_months(getdate(self.accrual_date), -1)))
        )

        rs = self._settlement()
        self._approve(rs)
        self.assertEqual(rs.docstatus, 1)
        self.assertEqual(rs.status, "Approved")

        for n in (in1, in2):
            s = _settled(n)
            self.assertEqual(s.settled, 1, f"{n} must be settled after approve")
            self.assertEqual(s.rental_settlement, rs.name, f"{n} must link to the settlement")

        # Untouched: other office, other period.
        self.assertEqual(_settled(other_office).settled, 0)
        self.assertIsNone(_settled(other_office).rental_settlement)
        self.assertEqual(_settled(prev_period).settled, 0)

    # --- idempotent: Approve then Mark Paid, and a second settlement ----------

    def test_stamp_is_idempotent_across_postsubmit_saves(self):
        row = self._accrual_row(self.office, self.accrual_date)
        rs = self._settlement()
        self._approve(rs)
        self.assertEqual(_settled(row).settled, 1)

        # Mark Paid is a second post-submit save -> on_update_after_submit fires
        # again. The row is already settled, so stamp_settlement must touch
        # nothing and the link must stay on the SAME settlement.
        self._mark_paid(rs)
        s = _settled(row)
        self.assertEqual(s.settled, 1)
        self.assertEqual(s.rental_settlement, rs.name)

        # Direct re-stamp call is a no-op (returns 0 newly-stamped).
        n = rental_engine.stamp_settlement(rs.name, self.office, self.period)
        self.assertEqual(n, 0, "Re-stamping an already-settled period must stamp 0 rows.")

    def test_second_settlement_finds_nothing_to_stamp(self):
        row = self._accrual_row(self.office, self.accrual_date)
        rs1 = self._settlement()
        self._approve(rs1)
        self.assertEqual(_settled(row).rental_settlement, rs1.name)

        # A second settlement for the same office+period must NOT re-point the
        # already-settled row.
        rs2 = self._settlement()
        self._approve(rs2)
        self.assertEqual(
            _settled(row).rental_settlement, rs1.name,
            "An already-settled row must never be re-pointed to a second settlement.",
        )

    # --- release on cancel ---------------------------------------------------

    def test_cancel_releases_rows(self):
        row = self._accrual_row(self.office, self.accrual_date)
        rs = self._settlement()
        self._approve(rs)
        self.assertEqual(_settled(row).settled, 1)

        frappe.set_user("Administrator")
        frappe.get_doc("Rental Settlement", rs.name).cancel()
        s = _settled(row)
        self.assertEqual(s.settled, 0, "Cancel must release the row (settled = 0).")
        self.assertIsNone(s.rental_settlement, "Cancel must clear the settlement link.")

    # --- report Settled / Outstanding split reflects reality -----------------

    def test_report_split_reflects_stamping(self):
        self._accrual_row(self.office, self.accrual_date, amount=100)
        self._accrual_row(self.office, self.accrual_date, amount=150)

        # Before settlement: all outstanding.
        _, before = rental_cost_by_office(
            {"rental_office": self.office,
             "from_date": self.accrual_date, "to_date": self.accrual_date}
        )
        bucket_before = next(r for r in before if r["rental_office"] == self.office)
        self.assertEqual(flt(bucket_before["settled_amount"]), 0.0)
        self.assertEqual(flt(bucket_before["outstanding_amount"]), 250.0)

        rs = self._settlement()
        self._approve(rs)

        # After: the same 250 now shows as settled, outstanding zero.
        _, after = rental_cost_by_office(
            {"rental_office": self.office,
             "from_date": self.accrual_date, "to_date": self.accrual_date}
        )
        bucket_after = next(r for r in after if r["rental_office"] == self.office)
        self.assertEqual(flt(bucket_after["settled_amount"]), 250.0)
        self.assertEqual(flt(bucket_after["outstanding_amount"]), 0.0)

    # --- accrued_total cross-check / derivation ------------------------------

    def test_accrued_total_derived_from_ledger_when_no_lines(self):
        # 100 + 150 accrued in the ledger; settlement has NO vehicle lines, so
        # accrued_total must be DERIVED from the ledger and the cross-check fields
        # populated.
        self._accrual_row(self.office, self.accrual_date, amount=100)
        self._accrual_row(self.office, self.accrual_date, amount=150)
        rs = self._settlement(claimed=300)
        rs.reload()
        self.assertEqual(flt(rs.ledger_accrued_total), 250.0)
        self.assertEqual(flt(rs.accrued_total), 250.0,
                         "With no vehicle lines, accrued_total must derive from the ledger.")
        self.assertEqual(flt(rs.ledger_variance), 0.0)
        # claimed 300 vs accrued 250 -> variance 50.
        self.assertEqual(flt(rs.variance), 50.0)

    def test_ledger_variance_surfaces_line_disagreement(self):
        # Ledger says 250, but the hand-entered line claims only 200 accrued ->
        # ledger_variance must surface the -50 gap (entered lines vs reality).
        self._accrual_row(self.office, self.accrual_date, amount=250)
        rs = self._settlement(
            claimed=200,
            vehicles=[{"vehicle": self.vehicle, "days": 2, "daily_rate": 100, "amount": 200}],
        )
        rs.reload()
        self.assertEqual(flt(rs.accrued_total), 200.0, "Entered lines drive accrued_total.")
        self.assertEqual(flt(rs.ledger_accrued_total), 250.0)
        self.assertEqual(flt(rs.ledger_variance), -50.0,
                         "ledger_variance must expose the lines-vs-ledger gap.")

    # --- monthly reconciliation ---------------------------------------------

    def test_monthly_reconciliation_flags_unsettled_closed_period(self):
        # The job flags the CLOSED period (last month). Seed an unsettled row in
        # last month for a dedicated office and assert exactly one alert.
        recon_office = self._office("RAL Recon Closed Office")
        closed_anchor = getdate(add_months(getdate(today()), -1))
        closed_date = str(get_first_day(closed_anchor))
        closed_period = str(closed_anchor)[:7]
        self._accrual_row(recon_office, closed_date, amount=500)

        def _count():
            return frappe.db.count(
                "Operations Alert",
                {"alert_type": "Unsettled Rental",
                 "message": ["like", f"%(office {recon_office})%"]},
            )

        frappe.db.delete(
            "Operations Alert",
            {"alert_type": "Unsettled Rental", "message": ["like", f"%(office {recon_office})%"]},
        )
        self.addCleanup(lambda: frappe.db.delete(
            "Operations Alert",
            {"alert_type": "Unsettled Rental", "message": ["like", f"%(office {recon_office})%"]},
        ))

        rental_engine.monthly_rental_reconciliation()
        first = _count()
        # Idempotent: a second run must not raise a duplicate.
        rental_engine.monthly_rental_reconciliation()
        second = _count()
        self.assertEqual(first, 1, "Closed-period unsettled office must raise exactly one alert.")
        self.assertEqual(second, 1, "Re-running reconciliation must not duplicate the alert.")
        # Sanity: the closed period string is what the alert message carries.
        self.assertIn(
            closed_period,
            frappe.db.get_value(
                "Operations Alert",
                {"alert_type": "Unsettled Rental", "message": ["like", f"%(office {recon_office})%"]},
                "message",
            ),
        )
