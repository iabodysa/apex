"""Tests for the Payment Router (config-time, mapping-driven dispatch).

Proves the construct end to end against a real, finance-approved Salis Payment
Request:

  * the config-driven field map builds the target payment document - both
    mapped (copy from source) and static (constant) rows;
  * idempotency - a second route returns the same payment, creates nothing new;
  * an unconfigured router (no target DocType) throws a clear message;
  * a not-yet-approved request throws and creates nothing;
  * auto_submit_target submits a submittable target;
  * the request is stamped with linked_payment_entry.

Two targets are exercised: a real core DocType (Note) with no dependencies for
the mapping/idempotency/auto-submit-off path, and a throwaway submittable stub
DocType for the auto-submit path. The whitelisted POST endpoint's HTTP-method
guard is locked by tests/test_http_enforcement.py.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.payment_router import route_payment, create_routed_payment

SETTINGS = "Payment Routing Settings"
STUB_DOCTYPE = "Test Routed Payment Stub"


def _make_stub_submittable_doctype():
    """Create a throwaway submittable DocType used as a target payment doc.

    Has a Data field (party) and a Currency field (paid_amount) so the field map
    has something concrete to populate, and is_submittable=1 to exercise the
    auto_submit_target path. Idempotent across reruns.
    """
    if frappe.db.exists("DocType", STUB_DOCTYPE):
        return
    frappe.get_doc(
        {
            "doctype": "DocType",
            "name": STUB_DOCTYPE,
            "module": "Apex Core",
            "custom": 1,
            "is_submittable": 1,
            "autoname": "hash",
            "fields": [
                {"fieldname": "party", "fieldtype": "Data", "label": "Party"},
                {"fieldname": "paid_amount", "fieldtype": "Currency", "label": "Paid Amount"},
                {"fieldname": "note", "fieldtype": "Small Text", "label": "Note"},
            ],
            "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1}],
        }
    ).insert(ignore_permissions=True)


class TestPaymentRouter(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        _make_stub_submittable_doctype()

    @classmethod
    def tearDownClass(cls):
        # DocType creation is DDL (not rolled back by FrappeTestCase). Drop the
        # throwaway target so the site is left clean after the run.
        frappe.set_user("Administrator")
        if frappe.db.exists("DocType", STUB_DOCTYPE):
            frappe.delete_doc("DocType", STUB_DOCTYPE, force=1, ignore_permissions=True)
            frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        # Reset the Single to a known-empty state before each test.
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = None
        s.auto_submit_target = 0
        s.set("field_map", [])
        s.save(ignore_permissions=True)

    # ------------------------------------------------------------------ helpers

    def _approved_request(self, **overrides):
        """An approved (finance-stamped, submitted) Salis Payment Request.

        Inserted and approved as Administrator (a System Manager, which is a
        finance authority) directly via the status field; the controller's
        finance gate stamps the approver. Bypasses the workflow UI - the router
        only cares that the request is finance-approved, however it got there.
        """
        data = {
            "doctype": "Salis Payment Request",
            "expense_type": "Rental",
            "amount": 1234.50,
            "remarks": "Router test request",
            "status": "Draft",
        }
        data.update(overrides)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        doc.submit()
        # Enter the Finance-gated state; the controller stamps finance_approved_by.
        doc.status = "Approved by Finance"
        doc.save(ignore_permissions=True)
        doc.reload()
        return doc

    def _configure(self, target, field_map, auto_submit=0):
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = target
        s.auto_submit_target = auto_submit
        s.set("field_map", field_map)
        s.save(ignore_permissions=True)
        return s

    # ------------------------------------------------------- unconfigured guard

    def test_unconfigured_target_throws(self):
        pr = self._approved_request()
        # No target_payment_doctype set (reset in setUp).
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(pr.name)
        self.assertIn("Payment Routing Settings", str(cm.exception))
        # Nothing was stamped.
        pr.reload()
        self.assertFalse(pr.linked_payment_entry)

    # ------------------------------------------------------- approval guard

    def test_not_approved_request_throws(self):
        # A draft (un-approved) request: insert only, no finance stamp.
        pr = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Fuel",
                "amount": 50,
                "status": "Draft",
            }
        )
        pr.insert(ignore_permissions=True)
        self.assertFalse(pr.finance_approved_by)

        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(pr.name)
        self.assertIn("not finance-approved", str(cm.exception))

    # ------------------------------------------------------- config-driven map

    def test_field_map_builds_target(self):
        pr = self._approved_request(amount=987.00, remarks="Pay the office")
        # Mapped rows copy from source; a static row writes a constant.
        self._configure(
            "Note",
            [
                {"target_fieldname": "title", "source_fieldname": "name"},
                {"target_fieldname": "content", "source_fieldname": "remarks"},
                {"target_fieldname": "public", "is_static": 1, "static_value": "1"},
            ],
        )
        created = route_payment(pr.name)
        self.assertTrue(frappe.db.exists("Note", created))

        note = frappe.get_doc("Note", created)
        # Mapped from source.
        self.assertEqual(note.title, pr.name)
        self.assertEqual(note.content, "Pay the office")
        # Static constant applied.
        self.assertEqual(int(note.public), 1)

        # The request is stamped with the created payment name.
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    # ------------------------------------------------------- idempotency

    def test_idempotent_second_call_returns_same(self):
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])

        first = route_payment(pr.name)
        notes_after_first = frappe.db.count("Note")

        # Second call must NOT create another payment; returns the same name.
        second = route_payment(pr.name)
        self.assertEqual(first, second)
        self.assertEqual(frappe.db.count("Note"), notes_after_first)

    def test_whitelisted_endpoint_routes(self):
        # The POST endpoint delegates to route_payment.
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        created = create_routed_payment(pr.name)
        self.assertTrue(frappe.db.exists("Note", created))
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    # ------------------------------------------------------- auto-submit + meta

    def test_auto_submit_submits_submittable_target(self):
        pr = self._approved_request(amount=555.00)
        self._configure(
            STUB_DOCTYPE,
            [
                {"target_fieldname": "paid_amount", "source_fieldname": "amount"},
                {"target_fieldname": "party", "is_static": 1, "static_value": "AFMCO"},
            ],
            auto_submit=1,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 1)  # submitted
        self.assertEqual(float(target.paid_amount), 555.00)
        self.assertEqual(target.party, "AFMCO")

    def test_no_auto_submit_leaves_draft(self):
        pr = self._approved_request()
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=0,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)  # left in Draft for review
