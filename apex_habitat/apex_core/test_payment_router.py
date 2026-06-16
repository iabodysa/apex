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
        # [#nhevq4]
        frappe.set_user("Administrator")
        if frappe.db.exists("DocType", STUB_DOCTYPE):
            frappe.delete_doc("DocType", STUB_DOCTYPE, force=1, ignore_permissions=True)
            frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        # [#j22s37]
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = None
        s.auto_submit_target = 0
        s.set("field_map", [])
        s.save(ignore_permissions=True)
        # [#5hd2hx]
        self._set_gl_posting(False)

    # [#f9hua6]

    def _set_gl_posting(self, enabled):
        """Flip the app-wide enable_gl_posting flag the router's GL gate reads."""
        apex = frappe.get_single("Apex Settings")
        apex.enable_gl_posting = 1 if enabled else 0
        apex.save(ignore_permissions=True)

    def _approved_request(self, **overrides):
        """An approved (finance-STAMPED, submitted) Salis Payment Request.

        The router gates on the immutable ``finance_approved_by`` stamp the
        controller's finance gate writes on a real approval (proven end to end in
        test_salis_payment_request_workflow). Here that stamp is set directly as a
        fixture so the router tests stay focused on routing: a request whose status
        is finance-gated but that carries NO stamp does not route
        (test_paid_status_without_finance_stamp_does_not_route).
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
        # [#j5jo49]
        doc.status = "Approved by Finance"
        doc.save(ignore_permissions=True)
        doc.db_set("finance_approved_by", "Administrator", update_modified=False)
        doc.reload()
        return doc

    def _configure(self, target, field_map, auto_submit=0):
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = target
        s.auto_submit_target = auto_submit
        s.set("field_map", field_map)
        s.save(ignore_permissions=True)
        return s

    # [#6b1p7m]

    def test_default_target_is_native_payment_request(self):
        # [#mmhyr3]
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
        # [#9p959q]
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
        # [#hoplry]
        with (
            patch(f"{pr_mod}.get_amount", return_value=750.00),
            patch(f"{pr_mod}.get_existing_payment_request_amount", return_value=0),
        ):
            created = route_payment(pr.name)

        # [#3vgho2]
        self.assertTrue(frappe.db.exists("Payment Request", created))
        built = frappe.get_doc("Payment Request", created)
        self.assertEqual(built.doctype, "Payment Request")
        self.assertEqual(built.reference_doctype, SOURCE_DOCTYPE)
        self.assertEqual(built.reference_name, pr.name)
        self.assertEqual(float(built.grand_total), 750.00)
        # [#nmut1t]
        self.assertTrue(built.currency, "router must default the target currency")

        # [#12z6l1]
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    # [#nxo01o]

    def test_not_approved_request_throws(self):
        # [#7sj7h2]
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

    def test_paid_status_without_finance_stamp_does_not_route(self):
        """A request whose STATUS is finance-gated but that carries NO
        ``finance_approved_by`` stamp must NOT route a payment (T-150).

        The stamp is the controller's durable proof the finance gate (role + SoD)
        actually ran. ``status`` is the mutable workflow_state field; a write that
        bypasses the controller's ``validate`` -- modelled here by a direct
        ``db.set_value`` -- can land "Paid" without ever clearing the gate. The
        router must trust the immutable stamp, not the status, and fail closed.
        """
        pr = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Fuel",
                "amount": 50,
                "status": "Draft",
            }
        )
        pr.insert(ignore_permissions=True)
        # [#9ptnct]
        frappe.db.set_value("Salis Payment Request", pr.name, "status", "Paid", update_modified=False)
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertFalse(pr.finance_approved_by, "no finance stamp on the bypass path")

        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        notes_before = frappe.db.count("Note")
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(pr.name)
        self.assertIn("not finance-approved", str(cm.exception))
        # [#bgiokc]
        self.assertEqual(frappe.db.count("Note"), notes_before)

    def test_forged_finance_stamp_is_stripped_and_does_not_route(self):
        """A caller-supplied ``finance_approved_by`` must NOT survive and must NOT
        route (the relocated-bypass guard).

        The router gates on the stamp, so the stamp itself must be server-owned.
        ``read_only`` is UI-only and the field is permlevel 0, so a role with
        create/write could otherwise forge it at insert under a non-gated status -
        where the finance gate early-returns and never inspects it. The controller
        reverts any value the gate did not write, so the forgery is stripped and
        the request never routes.
        """
        pr = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Fuel",
                "amount": 100,
                "status": "Draft",
                "finance_approved_by": "Administrator",  # [#teeu2f]
            }
        )
        pr.insert(ignore_permissions=True)
        pr.reload()
        self.assertFalse(
            pr.finance_approved_by,
            "server-owned stamp must be stripped when the finance gate did not write it",
        )

        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        notes_before = frappe.db.count("Note")
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(pr.name)
        self.assertIn("not finance-approved", str(cm.exception))
        self.assertEqual(frappe.db.count("Note"), notes_before)

    # [#s1tyq2]

    def test_field_map_builds_target(self):
        pr = self._approved_request(amount=987.00, remarks="Pay the office")
        # [#tkhqse]
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
        # [#a4vb9h]
        self.assertEqual(note.title, pr.name)
        self.assertEqual(note.content, "Pay the office")
        # [#7w9xgi]
        self.assertEqual(int(note.public), 1)

        # [#pl04zt]
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    # [#mxp9eu]

    def test_idempotent_second_call_returns_same(self):
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])

        first = route_payment(pr.name)
        notes_after_first = frappe.db.count("Note")

        # [#idiro9]
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
        # [#4km5p0]
        self.assertEqual(frappe.db.count("Note"), notes_before)

    def test_whitelisted_endpoint_routes(self):
        # [#bmi2c4]
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        created = create_routed_payment(pr.name)
        self.assertTrue(frappe.db.exists("Note", created))
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    # [#c7o16k]

    def test_auto_submit_submits_submittable_target_when_gl_on(self):
        # [#lwpe1f]
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
        self.assertEqual(target.docstatus, 1)  # [#ex515h]
        self.assertEqual(float(target.paid_amount), 555.00)
        self.assertEqual(target.party, "AFMCO")

    def test_auto_submit_blocked_when_gl_off_leaves_draft(self):
        # [#3r5w8w]
        pr = self._approved_request(amount=321.00)
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=1,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)  # [#p63ok1]
        # [#56enlx]
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    def test_no_auto_submit_leaves_draft(self):
        # [#ck9w8i]
        self._set_gl_posting(True)
        pr = self._approved_request()
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=0,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)  # [#ey7eni]
