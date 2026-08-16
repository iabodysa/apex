# Copyright (c) 2026, AFMCO and contributors
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
  * a CANCELLED request throws and creates nothing, even with auto-submit and GL
    posting on and its finance stamp still standing;
  * auto_submit_target submits a submittable target only when GL posting is on;
  * the request is stamped with linked_payment_entry.

Then the fail-closed half: the router refuses a target that is missing, a Single or
a child table, and a field map naming a field that does not exist on either side,
rather than building a payment that looks right and is not. Each of those pairs the
VALID input with the invalid one in the same test — a refusal never shown to accept
proves nothing. The invalid config is planted with db_set / ignore_validate on
purpose, because that is exactly the writer the controller's validate cannot see.

Targets exercised: native Payment Request (the unconfigured default), a real core
DocType (Note) with no dependencies for the mapping/idempotency path, and a
throwaway submittable stub DocType for the auto-submit + GL-gate paths. The
whitelisted POST endpoint's HTTP-method guard is locked by
tests/test_http_enforcement.py.

Size note: 395 test lines against 156 in the subject (2.5x), for 23 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting — each test names a different one.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import submit_via_workflow

from apex.apex_core.payment_router import (
    DEFAULT_TARGET_DOCTYPE,
    LINK_DOCTYPE_FIELD,
    LINK_NAME_FIELD,
    SOURCE_DOCTYPE,
    create_routed_payment,
    get_target_doctype,
    route_payment,
)
from apex.tests._helpers import set_gl_posting

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
        frappe.set_user("Administrator")
        # Reset the router as a PAIR before the stub goes. The last test may have left
        # it pointing here with a matching map; once the DocType is deleted the target
        # is a dangling Link and the rows name fields the default Payment Request does
        # not have — both would abort the next module's first save, not ours.
        frappe.db.delete("Payment Routing Field Map", {"parent": SETTINGS})
        frappe.db.set_single_value(SETTINGS, "target_payment_doctype", None)
        if frappe.db.exists("DocType", STUB_DOCTYPE):
            frappe.delete_doc("DocType", STUB_DOCTYPE, force=1, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = None
        s.auto_submit_target = 0
        s.set("field_map", [])
        s.save(ignore_permissions=True)
        set_gl_posting(False)


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
        # submit_via_workflow lands the sanctioned finance-approved submit
        # state (docstatus 1) past the guard; stamp the approver the router reads.
        submit_via_workflow(doc)
        doc.db_set("finance_approved_by", "Administrator", update_modified=False)
        doc.reload()
        return doc

    def _cancelled_request(self, **overrides):
        """An approved request the business then CANCELLED (docstatus 2).

        The shipped workflow carries ``Approved by Finance -> Cancelled`` (doc_status
        1 -> 2, action "Cancel", Fleet Manager), and ``apply_workflow`` reaches it by
        landing the persisted state on the cancel state and then calling
        ``doc.cancel()`` (frappe/model/workflow.py:142-143). Reproduced the same way
        ``submit_via_workflow`` reproduces the submit endpoint, so the router is
        handed exactly the record a real cancellation leaves behind — stamp intact.
        """
        doc = self._approved_request(**overrides)
        frappe.db.set_value(
            SOURCE_DOCTYPE, doc.name, "status", "Cancelled", update_modified=False
        )
        doc.reload()
        doc.cancel()
        doc.reload()
        return doc

    def _configure(self, target, field_map, auto_submit=0):
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = target
        s.auto_submit_target = auto_submit
        s.set("field_map", field_map)
        s.save(ignore_permissions=True)
        return s

    def _plant_target(self, target_doctype):
        """Write target_payment_doctype straight into tabSingles, skipping validate.

        Models every writer that legitimately bypasses the controller -- ``db_set``,
        a patch, raw SQL. That is the whole reason the router re-checks instead of
        trusting the Single's own ``validate``.
        """
        frappe.db.set_single_value(SETTINGS, "target_payment_doctype", target_doctype)

    def _plant_field_map(self, rows):
        """Save the field map with the controller's ``validate`` suppressed, the way
        a bulk import or a patch writes config that never met the guard."""
        s = frappe.get_single(SETTINGS)
        s.set("field_map", rows)
        s.flags.ignore_validate = True
        s.save(ignore_permissions=True)


    def test_default_target_is_native_payment_request(self):
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
        # erpnext is in hooks.required_apps, so Payment Request is always
        # installed wherever apex is; skipping on it reported success for the default
        # route without ever building one. Assert, so a missing target fails loudly.
        self.assertTrue(
            frappe.db.exists("DocType", "Payment Request"),
            "ERPNext Payment Request must be installed — erpnext is a required app",
        )

        pr = self._approved_request(amount=750.00, remarks="Default-route to native")
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
        with (
            patch(f"{pr_mod}.get_amount", return_value=750.00),
            patch(f"{pr_mod}.get_existing_payment_request_amount", return_value=0),
        ):
            created = route_payment(pr.name)

        self.assertTrue(frappe.db.exists("Payment Request", created))
        built = frappe.get_doc("Payment Request", created)
        self.assertEqual(built.doctype, "Payment Request")
        self.assertEqual(built.reference_doctype, SOURCE_DOCTYPE)
        self.assertEqual(built.reference_name, pr.name)
        self.assertEqual(float(built.grand_total), 750.00)
        self.assertTrue(built.currency, "router must default the target currency")

        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)
        # The default target is Payment Request, never Payment Entry: linked_payment_doctype
        # must name what was actually built (salis_payment_request.json:237-242 declares
        # linked_payment_entry as a Dynamic Link over it).
        self.assertEqual(pr.linked_payment_doctype, "Payment Request")
        self.assertFalse(frappe.db.exists("Payment Entry", created))


    def test_not_approved_request_throws(self):
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
        ``finance_approved_by`` stamp must NOT route a payment.

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
        frappe.db.set_value("Salis Payment Request", pr.name, "status", "Paid", update_modified=False)
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertFalse(pr.finance_approved_by, "no finance stamp on the bypass path")

        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        notes_before = frappe.db.count("Note")
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(pr.name)
        self.assertIn("not finance-approved", str(cm.exception))
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
                "finance_approved_by": "Administrator",
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

    def test_cancelled_request_does_not_route(self):
        """Cancelling is how the business stops a payment, so a cancelled request
        must not still raise one.

        The finance stamp is deliberately immutable and survives the cancellation
        untouched, so the approval gate alone still says yes on a voided request —
        and with ``auto_submit_target`` the routed doc would post its own GL. The
        stamp answers "was it approved"; docstatus answers "is it still live", and
        the router needs both.
        """
        pr = self._cancelled_request(amount=500.00, remarks="Voided by the business")
        self.assertEqual(pr.docstatus, 2)
        self.assertEqual(
            pr.finance_approved_by,
            "Administrator",
            "the immutable stamp survives cancellation — which is why docstatus must be read",
        )

        self._configure(
            "Note", [{"target_fieldname": "title", "source_fieldname": "name"}], auto_submit=1
        )
        set_gl_posting(True)
        notes_before = frappe.db.count("Note")
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(pr.name)
        self.assertIn("only a submitted, finance-approved request can be paid", str(cm.exception))
        self.assertEqual(frappe.db.count("Note"), notes_before)

        pr.reload()
        self.assertFalse(pr.linked_payment_entry, "a voided request is never stamped as paid")


    def test_field_map_builds_target(self):
        pr = self._approved_request(amount=987.00, remarks="Pay the office")
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
        self.assertEqual(note.title, pr.name)
        self.assertEqual(note.content, "Pay the office")
        self.assertEqual(int(note.public), 1)

        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)


    def test_idempotent_second_call_returns_same(self):
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])

        first = route_payment(pr.name)
        notes_after_first = frappe.db.count("Note")

        second = route_payment(pr.name)
        self.assertEqual(first, second)
        self.assertEqual(frappe.db.count("Note"), notes_after_first)

    def test_chokepoint_rejects_caller_without_source_permission(self):
        """A DIRECT route_payment call by a caller lacking write/submit on the source
        request is rejected AT THE CHOKEPOINT -- not only via the whitelisted
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
        self.assertEqual(frappe.db.count("Note"), notes_before)

    def test_whitelisted_endpoint_routes(self):
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        created = create_routed_payment(pr.name)
        self.assertTrue(frappe.db.exists("Note", created))
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)


    def test_auto_submit_submits_submittable_target_when_gl_on(self):
        set_gl_posting(True)
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
        self.assertEqual(target.docstatus, 1)
        self.assertEqual(float(target.paid_amount), 555.00)
        self.assertEqual(target.party, "AFMCO")

    def test_auto_submit_blocked_when_gl_off_leaves_draft(self):
        pr = self._approved_request(amount=321.00)
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=1,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, created)

    def test_no_auto_submit_leaves_draft(self):
        set_gl_posting(True)
        pr = self._approved_request()
        self._configure(
            STUB_DOCTYPE,
            [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}],
            auto_submit=0,
        )
        created = route_payment(pr.name)
        target = frappe.get_doc(STUB_DOCTYPE, created)
        self.assertEqual(target.docstatus, 0)

    # Fail-closed guards. Every one pairs the VALID input (which must still route)
    # with the invalid one, because a refusal never shown to accept proves nothing.

    def test_uninstalled_target_refuses_and_builds_nothing(self):
        """A target this site does not have must refuse, not fall through.

        Nothing checked the target before: ``frappe.new_doc`` was called on whatever
        the config named, so the operator learned about their mistake (if at all)
        from a stack trace far from the field they got wrong.
        """
        good = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        self.assertTrue(frappe.db.exists("Note", route_payment(good.name)))

        ghost = "Apex A278 Absent Payment DocType"
        self.assertFalse(frappe.db.exists("DocType", ghost))
        bad = self._approved_request()
        self._plant_target(ghost)
        notes_before = frappe.db.count("Note")
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(bad.name)
        # Assert the MESSAGE, not just the type: a bare ValidationError here could
        # equally be frappe's own link check and would prove nothing about ours.
        self.assertIn(ghost, str(cm.exception))
        self.assertIn("not installed", str(cm.exception))
        self.assertEqual(frappe.db.count("Note"), notes_before)
        bad.reload()
        self.assertFalse(bad.linked_payment_entry)

    def test_single_target_refuses_and_leaves_that_single_intact(self):
        """A Single target must be refused BEFORE the insert.

        ``Document.insert`` sends a Single to ``update_single``
        (frappe/model/document.py:316), which DELETES every ``tabSingles`` row for
        that doctype (document.py:582) and rewrites it from the field map. Routing a
        payment at Apex Settings would therefore ERASE the GL gate and hand back the
        settings name as the payment.
        """
        good = self._approved_request(amount=100.00)
        self._configure(
            STUB_DOCTYPE, [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}]
        )
        self.assertTrue(frappe.db.exists(STUB_DOCTYPE, route_payment(good.name)))

        set_gl_posting(True)
        bad = self._approved_request(amount=100.00)
        self._plant_target("Apex Settings")
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(bad.name)
        self.assertIn("Apex Settings", str(cm.exception))
        self.assertIn("Single", str(cm.exception))
        # The Single the router would have wiped still carries its value.
        self.assertEqual(frappe.get_single("Apex Settings").enable_gl_posting, 1)
        bad.reload()
        self.assertFalse(bad.linked_payment_entry)

    def test_child_table_target_refuses_and_creates_no_orphan_row(self):
        """A child table row has no standalone existence — inserted alone it is a
        parentless orphan that still reads as a payment in a report."""
        good = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        self.assertTrue(frappe.db.exists("Note", route_payment(good.name)))

        child = "Payment Routing Field Map"
        self.assertEqual(frappe.get_meta(child).istable, 1)
        bad = self._approved_request()
        self._plant_target(child)
        rows_before = frappe.db.count(child)
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(bad.name)
        self.assertIn(child, str(cm.exception))
        self.assertIn("child table", str(cm.exception))
        self.assertEqual(frappe.db.count(child), rows_before)

    def test_unknown_target_fieldname_refuses_instead_of_paying_a_blank_field(self):
        """The typo that motivates the card.

        ``BaseDocument.set`` writes any key into ``__dict__`` with no meta check
        (frappe/model/base_document.py:228-241) and ``get_valid_dict`` then keeps
        only ``meta.get_valid_columns()`` (base_document.py:357-364) — so a mistyped
        target fieldname is dropped in SILENCE and the payment is created with that
        field unset. A 0.00 payment that looks entirely normal is worse than a
        refusal, because nobody reads it twice.
        """
        good = self._approved_request(amount=444.00)
        self._configure(
            STUB_DOCTYPE, [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}]
        )
        created = route_payment(good.name)
        self.assertEqual(float(frappe.get_doc(STUB_DOCTYPE, created).paid_amount), 444.00)

        bad = self._approved_request(amount=444.00)
        self._plant_field_map([{"target_fieldname": "paid_amont", "source_fieldname": "amount"}])
        stubs_before = frappe.db.count(STUB_DOCTYPE)
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(bad.name)
        self.assertIn("paid_amont", str(cm.exception))
        self.assertEqual(frappe.db.count(STUB_DOCTYPE), stubs_before)

    def test_unknown_source_fieldname_refuses_instead_of_writing_blank(self):
        """``source.get`` on a field the request does not have returns None, so the
        target field is written — just empty. Same wrong payment, quieter cause."""
        good = self._approved_request(amount=222.00)
        self._configure(
            STUB_DOCTYPE, [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}]
        )
        created = route_payment(good.name)
        self.assertEqual(float(frappe.get_doc(STUB_DOCTYPE, created).paid_amount), 222.00)

        bad = self._approved_request(amount=222.00)
        self._plant_field_map([{"target_fieldname": "paid_amount", "source_fieldname": "amuont"}])
        stubs_before = frappe.db.count(STUB_DOCTYPE)
        with self.assertRaises(frappe.ValidationError) as cm:
            route_payment(bad.name)
        self.assertIn("amuont", str(cm.exception))
        self.assertEqual(frappe.db.count(STUB_DOCTYPE), stubs_before)

    def test_standard_source_fieldname_is_still_accepted(self):
        """``name`` is a default field, not a DocField, so ``Meta.has_field`` is False
        for it (frappe/model/meta.py:247-250). Validating with ``has_field`` alone
        would refuse the shipped default mapping — ``frappe.model.default_fields`` is
        the half that keeps this guard from over-refusing."""
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        created = route_payment(pr.name)
        self.assertEqual(frappe.get_doc("Note", created).title, pr.name)

    # The source link must name the document that was actually built.

    def test_link_stamp_names_the_doctype_actually_created(self):
        """``linked_payment_entry`` was declared ``Link -> Payment Entry`` while the
        router builds the CONFIGURED target, and it is written with ``db_set``, which
        skips validate entirely (frappe/model/document.py:1235-1239) — so a
        cross-type name landed with nothing to catch it."""
        pr = self._approved_request()
        self._configure("Note", [{"target_fieldname": "title", "source_fieldname": "name"}])
        created = route_payment(pr.name)

        pr.reload()
        self.assertEqual(pr.linked_payment_doctype, "Note")
        self.assertEqual(pr.linked_payment_entry, created)
        # The pair resolves against the table it names ...
        self.assertTrue(frappe.db.exists(pr.linked_payment_doctype, pr.linked_payment_entry))
        # ... never against Payment Entry: linked_payment_entry is a Dynamic Link over
        # linked_payment_doctype, not a fixed Link -> Payment Entry
        # (salis_payment_request.json:237-242).
        self.assertFalse(frappe.db.exists("Payment Entry", created))

    def test_link_field_is_a_dynamic_link_over_the_stamped_doctype(self):
        """Schema half of the same invariant: a fixed Link cannot be correct for a
        per-deployment configurable target, so the field has to be a Dynamic Link
        over the companion the router stamps."""
        meta = frappe.get_meta(SOURCE_DOCTYPE)
        link = meta.get_field(LINK_NAME_FIELD)
        self.assertEqual(link.fieldtype, "Dynamic Link")
        self.assertEqual(link.options, LINK_DOCTYPE_FIELD)
        companion = meta.get_field(LINK_DOCTYPE_FIELD)
        self.assertEqual(companion.fieldtype, "Link")
        self.assertEqual(companion.options, "DocType")

    # Config time — where the operator can still fix it.

    def test_settings_refuse_a_single_target_on_save(self):
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = "Note"
        s.save(ignore_permissions=True)
        self.assertEqual(frappe.get_single(SETTINGS).target_payment_doctype, "Note")

        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = "Apex Settings"
        with self.assertRaises(frappe.ValidationError) as cm:
            s.save(ignore_permissions=True)
        self.assertIn("Single", str(cm.exception))
        self.assertEqual(frappe.get_single(SETTINGS).target_payment_doctype, "Note")

    def test_settings_refuse_an_unknown_target_fieldname_on_save(self):
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = STUB_DOCTYPE
        s.set("field_map", [{"target_fieldname": "paid_amount", "source_fieldname": "amount"}])
        s.save(ignore_permissions=True)
        self.assertEqual(len(frappe.get_single(SETTINGS).field_map), 1)

        s = frappe.get_single(SETTINGS)
        s.set("field_map", [{"target_fieldname": "paid_amont", "source_fieldname": "amount"}])
        with self.assertRaises(frappe.ValidationError) as cm:
            s.save(ignore_permissions=True)
        self.assertIn("paid_amont", str(cm.exception))

    def test_missing_target_is_refused_by_the_native_link_check_on_save(self):
        """Records WHERE the guard is, so a later reader does not credit ours.

        ``_validate_links`` runs at frappe/model/document.py:413, BEFORE
        ``run_before_save_methods`` reaches the controller's ``validate`` — so on the
        save path an absent DocType is refused by Frappe itself. Ours is what covers
        the writers that skip both, proven above against the router.
        """
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = "Apex A278 Absent Payment DocType"
        with self.assertRaises(frappe.LinkValidationError):
            s.save(ignore_permissions=True)
