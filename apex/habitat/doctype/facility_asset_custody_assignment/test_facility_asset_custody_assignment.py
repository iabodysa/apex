# Copyright (c) 2026, afmcoltd
"""What Facility Asset Custody Assignment guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``before_submit``,
``on_submit`` and ``on_cancel``. Submission is refused on an empty asset table or one
not marked physically verified. Submitting hands every listed Facility Asset's
``responsible_supervisor`` to this assignment's supervisor; cancelling never simply
reverts that write — it hands the asset back to whichever OTHER submitted assignment
most recently held it, and leaves the asset's supervisor exactly as it stood when
nothing else ever held it.

"Facility Asset" is deliberately absent from ``test_dependencies``: its own dependency
graph reaches Asset -> Journal Entry -> ... -> Payment Gateway, a DocType this bench
does not have installed. Every asset this test needs is built directly below.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


def _fresh_asset():
    asset = frappe.copy_doc(frappe.get_test_records("Facility Asset")[0])
    asset.asset_name = f"_T-Custody Asset {frappe.generate_hash(length=6)}"
    asset.insert()
    return asset.name


def _new_assignment(supervisor, handover_date, asset=None, verified=1):
    record = frappe.copy_doc(frappe.get_test_records("Facility Asset Custody Assignment")[0])
    record.supervisor = supervisor
    record.witness = None
    record.handover_date = handover_date
    record.all_assets_verified = verified
    record.assets_in_custody = []
    if asset:
        record.append(
            "assets_in_custody", {"facility_asset": asset, "condition_at_handover": "Good"}
        )
    record.insert()
    return record


class TestFacilityAssetCustodyAssignment(FrappeTestCase):
    def test_submit_is_refused_on_an_empty_table_or_unverified_assets(self):
        """Both guards, then the acceptance case: verified assets hand over the asset."""
        asset = _fresh_asset()

        empty = _new_assignment("test2@example.com", "2026-01-20", asset=None, verified=1)
        with self.assertRaisesRegex(frappe.ValidationError, "Asset table cannot be empty"):
            empty.submit()

        unverified = _new_assignment("test2@example.com", "2026-01-21", asset=asset, verified=0)
        with self.assertRaisesRegex(frappe.ValidationError, "must be checked before submitting"):
            unverified.submit()

        verified = _new_assignment("test2@example.com", "2026-01-22", asset=asset, verified=1)
        verified.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "responsible_supervisor"),
            "test2@example.com",
        )

    def test_cancel_hands_the_asset_back_to_the_prior_holder_or_leaves_it_if_none(self):
        """A cancelled handover restores the previous custodian; with no previous
        custodian at all, the asset's supervisor is left exactly as it stood."""
        asset = _fresh_asset()

        first = _new_assignment("test2@example.com", "2026-01-01", asset=asset)
        first.submit()

        second = _new_assignment("test3@example.com", "2026-02-01", asset=asset)
        second.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "responsible_supervisor"),
            "test3@example.com",
        )

        second.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "responsible_supervisor"),
            "test2@example.com",
            "cancelling a handover must restore the prior submitted custodian",
        )

        first.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset, "responsible_supervisor"),
            "test2@example.com",
            "with no prior submitted assignment left, the asset's supervisor is untouched",
        )
