"""Tests for the Payment Router (config-time, mapping-driven dispatch).

Proves the construct end to end against a real, finance-approved Salis Payment
Request:

  * the config-driven field map builds the target payment document - both
    mapped (copy from source) and static (constant) rows;
  * idempotency - a second route returns the same payment, creates nothing new;
  * an unconfigured router defaults to the native Payment Request (no throw) -
    both the resolver default and a real default-build that creates an actual
    Payment Request row from an approved request;
  * a not-yet-approved request throws and creates nothing;
  * auto_submit_target submits a submittable target only when GL posting is on;
  * the request is stamped with linked_payment_entry.

Targets exercised: native Payment Request (the unconfigured default), a real core
DocType (Note) with no dependencies for the mapping/idempotency path, and a
throwaway submittable stub DocType for the auto-submit + GL-gate paths. The
whitelisted POST endpoint's HTTP-method guard is locked by
tests/test_http_enforcement.py.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.payment_router import (
    DEFAULT_TARGET_DOCTYPE,
    SOURCE_DOCTYPE,
    create_routed_payment,
    get_target_doctype,
    route_payment,
)

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
        # GL posting OFF by default (factory default); GL-gated tests opt in.
        self._set_gl_posting(False)

    # ------------------------------------------------------------------ helpers

    def _set_gl_posting(self, enabled):
        """Flip the app-wide enable_gl_posting flag the router's GL gate reads."""
        apex = frappe.get_single("Apex Settings")
        apex.enable_gl_posting = 1 if enabled else 0
        apex.save(ignore_permissions=True)

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

    # --------------------------------------------------- native-first default

    def test_default_target_is_native_payment_request(self):
        # With no target configured (reset in setUp), the resolver returns the
        # native primitive - never throws, never invents a custom DocType.
        s = frappe.get_single(SETTINGS)
        self.assertFalse(s.target_payment_doctype)
        self.assertEqual(get_target_doctype(s), "Payment Request")
        self.assertEqual(DEFAULT_TARGET_DOCTYPE, "Payment Request")

    def test_routes_to_native_payment_request_by_default(self):
        """An approved request, with the router unconfigured, builds a real native
        Payment Request and links it back.

        Payment Request is shipped by ERPNext; it is the standard payment-intent
        DocType (the native-first default). The field map supplies the fields its
        controller requires (``payment_request_type``, ``reference_doctype`` /
        ``reference_name`` -> the source request itself, ``grand_total``). The
        router defaults the target's ``currency`` (the source has none) so the
        native build is valid. ERPNext's ``validate`` additionally treats the
        reference as *invoice-shaped*, reading ``currency`` off it in two places -
        ``get_amount`` and ``get_existing_payment_request_amount``; a Salis Payment
        Request is not an invoice, so both couplings are patched (amount + the
        existing-PR lookup). Everything else - ``frappe.new_doc``, the field map,
        the currency default, the insert, the link stamp - is the real router path.
        """
        if not frappe.db.exists("DocType", "Payment Request"):
            self.skipTest("ERPNext Payment Request not installed on this site")

        pr = self._approved_request(amount=750.00, remarks="Default-route to native")
        # No target configured -> the router must default to Payment Request.
        self._configure(
            None,
            [
                {"target_fieldname": "payment_request_type", "is_static": 1, "static_value": "Outward"},
                {"target_fieldname": "reference_doctype", "is_static": 1, "static_value": SOURCE_DOCTYPE},
                {"target_fieldname": "reference_name", "source_fieldname": "name"},
                {"target_fieldname": "grand_total", "source_fieldname": "amount"},
                {"target_fieldname": "subject", "source_fieldname": "remarks"},
            ],
        )

        pr_mod = "erpnext.accounts.doctype.payment_request.payment_request"
        # Both invoice-shaped couplings on the (non-invoice) reference are patched:
        # get_amount -> the request amount; get_existing_payment_request_amount ->
        # 0 (no prior Payment Requests exist against this brand-new approved source).
        with (
            patch(f"{pr_mod}.get_amount", return_value=750.00),
            patch(f"{pr_mod}.get_existing_payment_request_amount", return_value=0),
        ):
            created = route_payment(pr.name)

        # A genuine Payment Request row was created (the native default): the row
        # exists in the Payment Request table itself.
        self.assertTrue(frappe.db.exists("Payment Request", created))
        built = frappe.get_doc("Payment Request", created)
        self.assertEqual(built.doctype, "Payment Request")
        self.assertEqual(built.reference_doctype, SOURCE_DOCTYPE)
        self.assertEqual(built.reference_name, pr.name)
        self.assertEqual(float(built.grand_total), 750.00)
        # The router defaulted the target currency the Salis source lacks, so the
        # native payment is currency-bearing (company default, else SAR baseline).
        self.assertTrue(built.currency, "router must default the target currency")

        # The request is stamped with the created native payment's name.
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

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

    def test_chokepoint_rejects_caller_without_source_permission(self):
        """A DIRECT route_payment call by a caller lacking write/submit on the source
        request is rejected AT THE CHOKEPOINT (T-148) -- not only via the whitelisted
        entry -- so a future direct caller can never reach the ignore_permissions
        insert/submit unchecked. A runtime check, unlike the static presence assertion
        in test_http_enforcement."""
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        notes_before = frappe.db.count("Note")
        user = "no-router-perm@example.com"
        if not frappe.db.exists("User", user):
            frappe.get_doc({
                "doctype": "User", "email": user, "first_name": "No Router Perm",
                "send_welcome_email": 0,
            }).insert(ignore_permissions=True)
        frappe.set_user(user)
        try:
            with self.assertRaises(frappe.PermissionError):
                route_payment(pr.name)
        finally:
            frappe.set_user("Administrator")
        # The gate threw BEFORE any side effect: no payment was created.
        self.assertEqual(frappe.db.count("Note"), notes_before)

    def test_whitelisted_endpoint_routes(self):
        # The POST endpoint delegates to route_payment.
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        created = create_routed_payment(pr.name)
        self.assertTrue(frappe.db.exists("Note", created))
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    # ------------------------------------------------- auto-submit + GL gate

    def test_auto_submit_submits_submittable_target_when_gl_on(self):
        # Submitting a payment doc fires its GL posting, so it requires the flag.
        self._set_gl_posting(True)
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

    def test_auto_submit_blocked_when_gl_off_leaves_draft(self):
        # GL gate: even with auto_submit on, GL posting OFF must NOT submit -
        # the routed payment stays in Draft so nothing reaches the ledger (the
        # operational-memo behaviour applied to routing). setUp left GL OFF.
        pr = self._approved_request(amount=321.00)
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=1,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)  # NOT submitted - GL gate held
        # Still routed and linked (the record is created; only the GL-driving
        # submit is withheld).
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    def test_no_auto_submit_leaves_draft(self):
        # Auto-submit off leaves Draft regardless of the GL flag; prove it even
        # with GL on so this is isolated from the gate.
        self._set_gl_posting(True)
        pr = self._approved_request()
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=0,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)  # left in Draft for review
