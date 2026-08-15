# Copyright (c) 2026, AFMCO and contributors
"""A-368 — a field an operator must fill AFTER submit is reachable after submit.

Five fields were filled at a moment the form had already locked them:
``Custody Handover.all_items_verified``, and ``supervisor_confirmed``,
``completion_photo``, ``visit_notes`` and ``actual_visit_date`` on Subcontractor
Service Order. None is ``allow_on_submit``.

Widening that flag would not have been enough, which is why the fix is a payload on
the existing whitelisted transition instead. Saving a submitted document is
``update_after_submit``, and Frappe gates that on the SUBMIT permission, not write
(``frappe/model/document.py:905-906``), while the people doing this work hold write.
Granting them submit to reach a notes box would also hand them authority to submit
and cancel the document they are executing.

Each test therefore does two things: proves the form path is still closed (so the
reason for the method has not quietly evaporated), and proves the method writes the
field on a docstatus-1 document.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.custody_handover import approve_handover
from apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order import (
    mark_completed,
)
from apex.tests.factories import make_goods_receipt


def _h(n=10):
    return frappe.generate_hash(length=n).upper()


class TestTheFormPathIsStillClosed(FrappeTestCase):
    """If these ever pass without raising, the methods below are no longer needed."""

    def test_the_five_fields_are_not_allow_on_submit(self):
        expected = {
            "Custody Handover": ["all_items_verified"],
            "Subcontractor Service Order": [
                "supervisor_confirmed",
                "completion_photo",
                "visit_notes",
                "actual_visit_date",
            ],
        }
        for doctype, fieldnames in expected.items():
            meta = frappe.get_meta(doctype)
            for fieldname in fieldnames:
                field = meta.get_field(fieldname)
                self.assertIsNotNone(field, f"{doctype}.{fieldname} is gone")
                self.assertFalse(
                    field.allow_on_submit,
                    f"{doctype}.{fieldname} became allow_on_submit — the payload "
                    "method may now be redundant, but check the SUBMIT-permission "
                    "gate at document.py:905 before removing it",
                )


class TestSubcontractorEvidenceReachesASubmittedOrder(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "SSO " + _h()}
        ).insert(ignore_permissions=True).name
        cls.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "SSO " + _h(),
                "site": cls.site,
                "total_capacity": 4,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name

    def _in_progress_order(self):
        doc = frappe.get_doc(
            {
                "doctype": "Subcontractor Service Order",
                "building": self.building,
                "scheduled_date": frappe.utils.today(),
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        doc.submit()
        doc.db_set("status", "In Progress")
        doc.reload()
        return doc

    def test_a_plain_save_of_the_evidence_is_refused_on_a_submitted_order(self):
        """The reason the payload method exists. If this stops raising, the form can
        carry the evidence and the method is no longer the only writer."""
        doc = self._in_progress_order()
        doc.visit_notes = "typed into the form"
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.save(ignore_permissions=True)

    def test_mark_completed_writes_every_evidence_field_after_submit(self):
        doc = self._in_progress_order()
        today = frappe.utils.today()
        mark_completed(
            doc.name,
            supervisor_confirmed=1,
            visit_notes="verified on site",
            actual_visit_date=today,
        )
        doc.reload()
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.status, "Completed")
        self.assertEqual(doc.supervisor_confirmed, 1)
        self.assertEqual(doc.visit_notes, "verified on site")
        self.assertEqual(str(doc.actual_visit_date), today)

    def test_passing_no_evidence_leaves_the_fields_untouched(self):
        """A caller that predates the payload must behave exactly as before."""
        doc = self._in_progress_order()
        mark_completed(doc.name)
        doc.reload()
        self.assertEqual(doc.status, "Completed")
        self.assertFalse(doc.supervisor_confirmed)
        self.assertIsNone(doc.visit_notes)


class TestHandoverVerificationIsAttestedAtApproval(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = frappe.db.get_value("Company", {})
        cc = frappe.db.get_value("Cost Center", {"is_group": 0})
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "HND " + _h()}
        ).insert(ignore_permissions=True).name
        cls.intake = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Intake " + _h(),
                "site": cls.site,
                "total_capacity": 4,
                "company": cls.company,
                "default_cost_center": cc,
                "is_procurement_store": 1,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        cls.dest = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Dest " + _h(),
                "site": cls.site,
                "total_capacity": 4,
                "company": cls.company,
                "default_cost_center": cc,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        category = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc(
            {"doctype": "Custody Asset Category", "category_name": "Cat " + _h()}
        ).insert(ignore_permissions=True).name
        cls.article = frappe.get_doc(
            {
                "doctype": "Custody Article",
                "naming_series": "ART-.####",
                "article_name": "Item " + _h(),
                "category": category,
                "unit_of_measure": "Nos",
            }
        ).insert(ignore_permissions=True).name
        # The controller refuses a handover whose two supervisors are the same person,
        # so the fixture needs two real accounts, not Administrator twice.
        cls.sender = cls._user()
        cls.receiver = cls._user()

    @classmethod
    def _user(cls):
        email = f"a368-{_h(12).lower()}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "U " + _h(),
                "send_welcome_email": 0,
            }
        )
        user.insert(ignore_permissions=True)
        user.add_roles("Accommodation Manager")
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        return email

    def _under_review_handover(self):
        # The controller refuses to hand over stock the store does not hold, so each
        # handover needs its own receipt first.
        make_goods_receipt(self.intake, self.article, self.sender, 2)
        doc = frappe.get_doc(
            {
                "doctype": "Custody Handover",
                "naming_series": "ACC-HND-.YYYY.-.#####",
                "handover_date": frappe.utils.today(),
                "from_building": self.intake,
                "to_building": self.dest,
                "procurement_supervisor": self.sender,
                "receiving_supervisor": self.receiver,
            }
        )
        doc.append("items", {"item_type": "Custody Article", "item": self.article, "qty": 2})
        doc.insert(ignore_permissions=True)
        doc.submit()
        doc.db_set("status", "Under Review")
        doc.reload()
        return doc

    def test_approval_without_the_attestation_is_still_refused(self):
        """The guard the card must not weaken: silence is not verification."""
        doc = self._under_review_handover()
        self.assertFalse(doc.all_items_verified)
        with self.assertRaises(frappe.exceptions.ValidationError):
            approve_handover(doc.name)

    def test_the_receiver_can_attest_at_approval_on_a_submitted_handover(self):
        doc = self._under_review_handover()
        self.assertEqual(doc.docstatus, 1)
        self.assertFalse(doc.all_items_verified)
        approve_handover(doc.name, all_items_verified=1)
        doc.reload()
        self.assertTrue(doc.all_items_verified)
        self.assertEqual(doc.status, "Approved")

    def test_a_handover_already_verified_still_approves_unchanged(self):
        """Backward compatibility: the pre-ticked path must not break."""
        doc = self._under_review_handover()
        doc.db_set("all_items_verified", 1)
        approve_handover(doc.name)
        doc.reload()
        self.assertEqual(doc.status, "Approved")
