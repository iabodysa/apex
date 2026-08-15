from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.building_license import building_license
from apex.habitat.tasks import maintenance


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
        """Every rule inside renew() used to be reachable only through the Revoked check,
        so the rest of the endpoint could be deleted with this file green."""
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
