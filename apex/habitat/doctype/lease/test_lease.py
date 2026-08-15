# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]



class TestAccommodationLease(FrappeTestCase):

    def test_create_valid_lease(self):
        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 8000,
            "first_payment_date": "2026-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.rent_amount, 8000)
        frappe.delete_doc("Lease", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_date_raises(self):
        from apex.habitat.doctype.lease.lease import validate

        doc = frappe.get_doc({
            "doctype": "Lease",
            "building": "QA-BLDG",
            "lease_start_date": "2026-06-01",
            "lease_end_date": "2026-05-01",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_schedule_rows_default_unpaid(self):
        """Generated schedule rows are stamped 'Unpaid', never 'Paid'. The
        'Generate Payment' button selects the next non-Paid row, so a fresh row
        must read Unpaid for that selection to land on it (guards the row-pick
        contract the form button depends on)."""
        from apex.habitat.doctype.lease.lease import _build_schedule

        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-06-30",
            "rent_amount": 4000,
            "first_payment_date": "2026-01-01",
            "billing_cycle": "Monthly",
        })
        _build_schedule(doc)
        self.assertTrue(doc.payment_schedule)
        self.assertTrue(all(r.status == "Unpaid" for r in doc.payment_schedule))


class TestRegenerateScheduleFailure(FrappeTestCase):
    """What a REFUSED ``regenerate_schedule`` costs the rest of the request.

    The endpoint used to wrap its ``doc.save()`` in ``except Exception:
    frappe.db.rollback(); frappe.throw(generic)``. ``frappe.db.rollback()`` takes no
    savepoint, so it discarded the WHOLE request transaction — every row written
    before this endpoint was reached, not just the lease — and reported "Could not
    save changes" in place of the validation error that actually refused the save.

    The refusal below is real, not injected: an existing lease is widened into an
    overlap with ``frappe.db.set_value`` (which skips validate), which is how live
    data drifts underneath a draft somebody left open.
    """

    def _hash(self):
        return frappe.generate_hash(length=12).upper()

    def _witness_row(self):
        """A Site row: one mandatory Data field, no links, untouched by anything else
        here, so its survival isolates the transaction behaviour."""
        return frappe.get_doc({
            "doctype": "Site", "site_name": "A333-LEASE-" + self._hash(),
        }).insert(ignore_permissions=True).name

    def _building(self):
        return frappe.get_doc({
            "doctype": "Building", "building_name": "B " + self._hash(), "total_capacity": 4,
        }).insert(ignore_permissions=True).name

    def _draft_lease(self, building, start, end):
        return frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": building,
            "lease_start_date": start,
            "lease_end_date": end,
            "rent_amount": 6000,
            "billing_cycle": "Monthly",
            "first_payment_date": start,
        }).insert(ignore_permissions=True)

    def test_a_refused_regeneration_keeps_rows_written_earlier_in_the_same_request(self):
        from apex.habitat.doctype.lease.lease import regenerate_schedule

        witness = self._witness_row()
        building = self._building()
        lease = self._draft_lease(building, "2026-01-01", "2026-12-31")
        rival = self._draft_lease(building, "2027-01-01", "2027-12-31")
        frappe.db.set_value("Lease", rival.name, "lease_start_date", "2026-06-01")

        with self.assertRaises(frappe.ValidationError) as caught:
            regenerate_schedule(lease.name)

        self.assertIn(
            rival.name, str(caught.exception),
            "the caller must be told WHICH lease overlaps, not a generic 'could not "
            "save changes' standing in for it",
        )
        self.assertTrue(
            frappe.db.exists("Site", witness),
            "a refused regeneration must not discard rows this request wrote before it",
        )
        self.assertTrue(
            frappe.db.exists("Lease", rival.name),
            "the overlapping lease that caused the refusal must survive it",
        )
