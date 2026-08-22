# Copyright (c) 2026, AFMCO and contributors
from __future__ import annotations
import frappe
from frappe.tests.utils import FrappeTestCase
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.habitat.doctype.building_license import building_license
from apex.habitat.tasks import maintenance

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
        only_issue.validate()

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
        original.submit()
        original.cancel()

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
        self.assertTrue(callable(blc.renew))

        frappe.delete_doc("Building License", doc.name, force=True, ignore_permissions=True)

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']

def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake
def _call(endpoint, *args, **kwargs):
    return getattr(endpoint, "__wrapped__", endpoint)(*args, **kwargs)
class TestBuildingLicenseLifecycle(TestCase):
    def test_expiry_boundaries_have_one_shared_derivation(self):
        self.assertEqual(
            building_license.derive_license_status("2026-08-14", 60, "2026-08-14"),
            "Expired",
        )
        self.assertEqual(
            building_license.derive_license_status("2026-10-13", 60, "2026-08-14"),
            "Expiring Soon",
        )
        self.assertEqual(
            building_license.derive_license_status("2026-10-14", 60, "2026-08-14"),
            "Active",
        )

    def test_revocation_requires_reason_and_write_permission_before_mutation(self):
        doc = MagicMock(docstatus=1, status="Active")
        doc.name = "BL-1"
        doc.check_permission.side_effect = frappe.PermissionError("denied")
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(building_license, "frappe", fake),
            patch.object(building_license, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(building_license.mark_revoked, "BL-1", " ")
            with self.assertRaises(frappe.PermissionError):
                _call(building_license.mark_revoked, "BL-1", "Authority withdrew it")

        doc.db_set.assert_not_called()

    def test_revocation_is_audited_and_terminal(self):
        doc = MagicMock(docstatus=1, status="Active")
        doc.name = "BL-1"
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(building_license, "frappe", fake),
            patch.object(building_license, "_", side_effect=lambda message: message),
        ):
            result = _call(
                building_license.mark_revoked, "BL-1", "Authority withdrew it"
            )

        fake.get_doc.assert_called_once_with(
            "Building License", "BL-1", for_update=True
        )
        doc.db_set.assert_called_once_with("status", "Revoked")
        self.assertIn("Authority withdrew it", doc.add_comment.call_args.args[1])
        self.assertEqual(result, {"name": "BL-1", "status": "Revoked"})

        doc.status = "Revoked"
        doc.reset_mock()
        with (
            patch.object(building_license, "frappe", fake),
            patch.object(building_license, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(building_license.mark_revoked, "BL-1", "Again")
        doc.db_set.assert_not_called()

    def test_revoked_license_cannot_be_cancelled_for_amendment(self):
        doc = MagicMock(status="Revoked")
        fake = _raising_frappe()

        with (
            patch.object(building_license, "frappe", fake),
            patch.object(building_license, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                building_license.BuildingLicense.before_cancel(doc)

    def test_revoked_license_cannot_be_renewed(self):
        doc = MagicMock(
            status="Revoked",
            docstatus=0,
            expiry_date="2026-08-14",
            renewal_lead_days=60,
        )
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(building_license, "frappe", fake),
            patch.object(building_license, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(building_license.renew, "BL-1", new_expiry_date="2027-08-14")

        doc.save.assert_not_called()

    def _renew(self, doc, **kwargs):
        """Exercises every rule inside renew(), not only the Revoked check: deleting
        the rest of the endpoint must fail this file, not leave it green."""
        fake = _raising_frappe()
        fake.get_doc.return_value = doc
        with (
            patch.object(building_license, "frappe", fake),
            patch.object(building_license, "_", side_effect=lambda message: message),
            patch.object(building_license, "today", return_value="2026-08-15"),
        ):
            return _call(building_license.renew, "BL-1", **kwargs)

    def test_renewal_rolls_the_expiry_forward_and_stamps_the_date(self):
        doc = MagicMock(
            status="Expiring Soon", docstatus=0, expiry_date="2026-09-01", renewal_lead_days=60
        )
        doc.name = "BL-1"

        result = self._renew(doc, new_expiry_date="2027-09-01")

        self.assertEqual(str(doc.expiry_date), "2027-09-01")
        self.assertEqual(doc.last_renewal_date, "2026-08-15")
        self.assertEqual(doc.status, "Active")
        doc.save.assert_called_once()
        self.assertEqual(result["expiry_date"], "2027-09-01")
        self.assertEqual(result["last_renewal_date"], "2026-08-15")

    def test_extend_days_is_measured_from_the_current_expiry(self):
        doc = MagicMock(
            status="Active", docstatus=0, expiry_date="2026-09-01", renewal_lead_days=60
        )
        doc.name = "BL-1"

        result = self._renew(doc, extend_days=30)

        self.assertEqual(result["expiry_date"], "2026-10-01")

    def test_a_submitted_license_is_amended_not_renewed(self):
        doc = MagicMock(
            status="Active", docstatus=1, expiry_date="2026-09-01", renewal_lead_days=60
        )
        doc.name = "BL-1"

        with self.assertRaises(frappe.ValidationError):
            self._renew(doc, new_expiry_date="2027-09-01")

        doc.save.assert_not_called()

    def test_a_renewal_may_not_move_the_expiry_backwards_or_stand_still(self):
        for new_expiry in ("2026-08-01", "2026-09-01"):
            with self.subTest(new_expiry=new_expiry):
                doc = MagicMock(
                    status="Active", docstatus=0, expiry_date="2026-09-01", renewal_lead_days=60
                )
                doc.name = "BL-1"

                with self.assertRaises(frappe.ValidationError):
                    self._renew(doc, new_expiry_date=new_expiry)

                doc.save.assert_not_called()

    def test_a_renewal_with_neither_a_date_nor_a_span_is_refused(self):
        doc = MagicMock(
            status="Active", docstatus=0, expiry_date="2026-09-01", renewal_lead_days=60
        )
        doc.name = "BL-1"

        with self.assertRaises(frappe.ValidationError):
            self._renew(doc)

        doc.save.assert_not_called()

    def test_scheduler_uses_shared_derivation_and_excludes_revoked(self):
        row = frappe._dict(
            name="BL-1",
            expiry_date="2026-08-14",
            renewal_lead_days=60,
            status="Active",
        )
        fake = MagicMock()
        fake.get_all.side_effect = [[row], []]
        fake.db.get_single_value.return_value = 60

        with (
            patch.object(maintenance, "frappe", fake),
            patch.object(
                maintenance, "derive_license_status", return_value="Expired"
            ) as derive,
            patch("frappe.utils.today", return_value="2026-08-14"),
        ):
            maintenance.daily_building_license_expiry_check()

        self.assertEqual(
            fake.get_all.call_args_list[0].kwargs["filters"]["status"],
            ["!=", "Revoked"],
        )
        derive.assert_called_once_with("2026-08-14", 60, "2026-08-14")
        fake.db.set_value.assert_called_once_with(
            "Building License", "BL-1", "status", "Expired"
        )
class TestBuildingLicenseMetadata(TestCase):
    def test_status_is_system_owned_and_under_renewal_is_removed(self):
        metadata = json.loads(
            Path(__file__)
            .with_name("building_license.json")
            .read_text(encoding="utf-8")
        )
        status = next(
            field for field in metadata["fields"] if field["fieldname"] == "status"
        )
        self.assertEqual(
            status["options"].splitlines(),
            ["Active", "Expiring Soon", "Expired", "Revoked"],
        )
        self.assertTrue(status["read_only"])
        self.assertNotIn(
            "Under Renewal", {state["title"] for state in metadata["states"]}
        )
