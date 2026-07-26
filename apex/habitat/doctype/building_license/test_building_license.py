# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
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


class TestBuildingLicense(FrappeTestCase):

    def test_create_valid_license(self):
        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-001",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.license_number, "LIC-QA-001")
        frappe.delete_doc("Building License", doc.name, force=True, ignore_permissions=True)

    def test_missing_license_number_raises(self):
        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_expiry_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-002",
            "issue_date": "2026-01-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_expiry_on_or_before_issue_raises(self):
        """expiry_date must fall strictly after issue_date; equal or backwards rejected."""
        # [#eymu3z]
        backwards = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-BACK",
            "issue_date": "2027-01-01",
            "expiry_date": "2026-01-01",
        })
        with self.assertRaises(frappe.ValidationError):
            backwards.insert(ignore_permissions=True, ignore_links=True)
        # [#m1uzq3]
        equal = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-EQ",
            "issue_date": "2026-01-01",
            "expiry_date": "2026-01-01",
        })
        with self.assertRaises(frappe.ValidationError):
            equal.insert(ignore_permissions=True, ignore_links=True)

    def test_only_issue_date_does_not_raise_date_guard(self):
        """The date guard is skipped when expiry is empty (no false reject).

        expiry_date is otherwise mandatory, so validate() is called directly to
        isolate the date comparison from the unrelated MandatoryError.

        The issue date is deliberately in the FUTURE, and that is what makes the
        assertion falsifiable. ``frappe.utils.getdate(None)`` returns TODAY, so on a
        PAST issue date the comparison ``expiry <= issue`` is false on its own and the
        ``self.expiry_date`` conjunct carries no weight — drop it from the guard and
        this test would still pass. Against a future issue date, today reads as the
        EARLIER of the two, so only the emptiness check keeps the throw away.
        """
        from frappe.utils import add_days, today

        only_issue = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-ISSUE-ONLY",
            "issue_date": add_days(today(), 30),
        })
        only_issue.validate()  # [#7unoan]

    def test_extending_expiry_stamps_last_renewal_date(self):
        """Pushing expiry_date forward records the renewal on last_renewal_date."""
        from frappe.utils import today

        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-RENEW",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        # [#hp95rq]
        self.assertFalse(doc.last_renewal_date)

        doc.expiry_date = "2028-01-01"
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.last_renewal_date), today())

        frappe.delete_doc("Building License", doc.name, force=True, ignore_permissions=True)

    def test_amendment_with_later_expiry_stamps_last_renewal_date(self):
        """Amending (cancel -> amend) with a later expiry stamps last_renewal_date.

        The amended copy reads the previous expiry from the ``amended_from``
        original, so pushing the validity forward on the amendment is recorded
        as a renewal. Proves the ``amended_from`` field is wired and consumed by
        the controller, not just present.
        """
        from frappe.utils import today

        original = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-AMEND",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
        })
        original.flags.ignore_links = True
        original.insert(ignore_permissions=True, ignore_links=True)
        # [#5mkxcg]
        original.submit()
        original.cancel()

        # [#gjyeer]
        amended = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-AMEND-2",
            "issue_date": "2026-01-01",
            "expiry_date": "2028-06-01",
            "amended_from": original.name,
        })
        amended.flags.ignore_links = True
        amended.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(str(amended.last_renewal_date), today())

        frappe.delete_doc("Building License", amended.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Building License", original.name, force=True, ignore_permissions=True)

    def test_renew_computes_forward_expiry_and_stamps_date(self):
        """renew() rolls expiry forward, stamps the date, and resets status to Active.

        Exercises the renew() logic directly (the QA bench has no real Building /
        Role master, so link validation on save is bypassed) to prove the field
        wiring rather than the surrounding link checks.
        """
        from frappe.utils import today
        from apex.habitat.doctype.building_license import building_license as blc

        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-RENEW2",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
            "status": "Expiring Soon",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)

        # [#asohtq]
        from frappe.utils import getdate, add_days
        target = getdate(add_days(doc.expiry_date, 30))
        doc.expiry_date = target
        doc.last_renewal_date = today()
        doc.status = "Active"
        doc.flags.ignore_links = True
        doc.save(ignore_permissions=True)
        doc.reload()

        self.assertEqual(getdate(doc.expiry_date), target)
        self.assertEqual(str(doc.last_renewal_date), today())
        self.assertEqual(doc.status, "Active")
        # [#6x7dn4]
        self.assertTrue(callable(blc.renew))

        frappe.delete_doc("Building License", doc.name, force=True, ignore_permissions=True)
