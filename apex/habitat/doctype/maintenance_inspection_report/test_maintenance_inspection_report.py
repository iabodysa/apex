# Copyright (c) 2026, afmcoltd
"""What Maintenance Inspection Report guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``on_submit``,
``on_cancel`` and ``before_cancel``. Submitting stamps the inspected Facility Asset's
``last_inspection_date``, but only forward — a report submitted out of date order must
never roll the stamp back. Cancelling never simply reverts the stamp (this may not be
the report that set it); it re-derives the date as the max over whatever submitted
reports remain, or clears it when none do. ``before_cancel`` requires a stated
cancellation reason before any of that unwinding runs.

NOTE for the owner: the module-level ``validate`` wired in ``hooks.py`` for this
DocType has an empty body (docstring only) — its docstring claims it "Blocks saving a
Maintenance Inspection Report that records no findings," but no such check exists, so
an empty-findings report currently inserts without refusal. No test asserts that
refusal here, since asserting it would fail against the DocType's actual current
behaviour; fixing the controller is outside this patch's write scope (test files only).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

test_dependencies = ["Building", "Employee"]


def _fresh_asset():
    asset = frappe.copy_doc(frappe.get_test_records("Facility Asset")[0])
    asset.asset_name = f"_T-Inspected Asset {frappe.generate_hash(length=6)}"
    asset.insert()
    return asset.name


def _new_report(asset, inspection_date):
    record = frappe.copy_doc(frappe.get_test_records("Maintenance Inspection Report")[0])
    record.facility_asset = asset
    record.inspection_date = inspection_date
    record.insert()
    return record


class TestMaintenanceInspectionReport(FrappeTestCase):
    def test_submit_only_advances_the_assets_stamp_and_cancel_recomputes_it(self):
        """The stamp must move forward on submit and re-derive, never simply revert, on cancel."""
        asset = _fresh_asset()

        earliest = _new_report(asset, "2026-01-10")
        earliest.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "last_inspection_date"),
            getdate(earliest.inspection_date),
        )

        latest = _new_report(asset, "2026-03-01")
        latest.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "last_inspection_date"),
            getdate(latest.inspection_date),
        )

        middle = _new_report(asset, "2026-02-01")
        middle.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "last_inspection_date"),
            getdate(latest.inspection_date),
            "a report submitted out of date order must not roll the stamp back",
        )

        latest.cancellation_reason = "Superseded finding, cancelling for correction"
        latest.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "last_inspection_date"),
            getdate(middle.inspection_date),
            "cancelling the report that set the stamp must re-derive it from what remains",
        )

    def test_cancel_is_refused_without_a_reason_and_clears_the_stamp_once_nothing_remains(self):
        """The guard and the empty-set case: no reason blocks cancel, and cancelling the
        last submitted report leaves nothing for the stamp to be derived from."""
        asset = _fresh_asset()
        record = _new_report(asset, "2026-04-01")
        record.submit()

        with self.assertRaisesRegex(frappe.ValidationError, "Cancellation Reason is required"):
            record.cancel()

        record.reload()
        record.cancellation_reason = "Asset scrapped before follow-up"
        record.cancel()

        self.assertIsNone(frappe.db.get_value("Facility Asset", asset, "last_inspection_date"))
