# Copyright (c) 2026, AFMCO and contributors
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
test_ignore = [
    "Housing Assignment",
    "Bed",
    "Building",
    "Room",
    "Site",
    "Additional Salary",
    "Accommodation Stock Ledger",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Custody Article",
    "Custody Asset Category",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "Transport Request",
    "User",
]


class TestAccommodationCheckout(FrappeTestCase):

    def test_create_valid_checkout(self):
        doc = frappe.get_doc({
            "doctype": "Housing Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_date": "2026-07-01",
            "checkout_reason": "End of Contract",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.checkout_reason, "End of Contract")
        frappe.delete_doc("Housing Checkout", doc.name, force=True, ignore_permissions=True)

    def test_missing_assignment_raises(self):
        doc = frappe.get_doc({
            "doctype": "Housing Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "checkout_date": "2026-07-01",
            "checkout_reason": "Final Exit",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_checkout_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Housing Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_reason": "Final Exit",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    # [#8qaw6l]

    def test_resolve_building_prefers_assignment(self):
        from apex.habitat.doctype.housing_checkout.housing_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": "QA-BLDG-A"})
        self.assertEqual(resolve_damage_assessment_building(assignment, None), "QA-BLDG-A")

    def test_resolve_building_assignment_wins_over_bed(self):
        # [#mv02qy]
        from apex.habitat.doctype.housing_checkout.housing_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": "QA-BLDG-A"})
        self.assertEqual(
            resolve_damage_assessment_building(assignment, "ANY-BED"), "QA-BLDG-A"
        )

    def test_resolve_building_returns_none_when_neither_side_has_one(self):
        """Both terms answer None, so the or-chain yields None on its own.

        Named for what it reaches: with no building anywhere the ``or None`` tail is
        not load-bearing (``None or None`` is already None), so this cannot detect its
        removal -- ``test_resolve_building_normalises_an_empty_bed_building`` is the
        case that can.
        """
        # [#pdkwyk]
        from apex.habitat.doctype.housing_checkout.housing_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": None})
        result = resolve_damage_assessment_building(assignment, "NONEXISTENT-BED")
        self.assertIsNone(result)
        self.assertNotEqual(result, "")

    def test_resolve_building_normalises_an_empty_bed_building(self):
        """The one input the ``or None`` tail exists for: a Bed row whose building
        column holds "" rather than NULL, which is what an unset Link on an EXISTING
        row actually stores.

        ``a or b or None`` returns b when both are falsy, so without the tail this
        answers "" -- a value that passes as set yet fails the mandatory Building
        link, silently dropping the assessment inside the best-effort try/except.
        Every sibling case feeds None, where the tail changes nothing.
        """
        from apex.habitat.doctype.housing_checkout import housing_checkout

        assignment = frappe._dict({"building": ""})
        with mock.patch.object(housing_checkout.frappe.db, "get_value", return_value=""):
            result = housing_checkout.resolve_damage_assessment_building(
                assignment, "BED-WITH-BLANK-BUILDING"
            )

        self.assertIsNone(
            result,
            'an empty building leaked out as "", which passes as a value and then '
            "fails the mandatory Building link",
        )

    def test_on_submit_locks_assignment_against_concurrent_checkout(self):
        """Regression (#4): two concurrent checkouts for one assignment must
        serialize and the loser must abort — on_submit re-reads the assignment's
        check_out_date under a row lock and throws when it is already set.

        True concurrency is not reproducible single-threaded, so the loser's race is
        played back against a recording db layer: the run must abort, and the read
        that decided it must have been a LOCKING read. Both are observed at the call
        boundary, so moving the lock into a helper or renaming its locals stays green
        while dropping for_update — the actual regression — does not.
        """
        from unittest.mock import MagicMock, patch
        from apex.habitat.doctype.housing_checkout import (
            housing_checkout as mod,
        )
        reads = []
        stub = MagicMock()
        stub.db.get_value.side_effect = lambda doctype, _name, field, **kw: (
            reads.append((doctype, field, kw.get("for_update"))) or "2026-07-01"
        )
        stub.throw.side_effect = frappe.ValidationError
        doc = frappe._dict(name="ACC-CHKOUT-QA", assignment="ACC-ASGN-QA",
                           checkout_date="2026-07-05")

        # `_` is swapped for identity so the run needs no translation cache.
        with patch.object(mod, "frappe", stub), patch.object(mod, "_", lambda text: text):
            with self.assertRaises(frappe.ValidationError):
                mod.on_submit(doc)

        self.assertIn(
            ("Housing Assignment", "check_out_date", True), reads,
            "the check_out_date re-read that decides the race must take a row lock",
        )

    # [#10md08]

    def test_on_submit_uses_correct_damage_assessment_fieldnames(self):
        """on_submit() auto-creates a draft Custody Damage Assessment carrying one
        row per Damaged/Lost custody return item, mapped onto the Custody Damage Item
        fieldnames 'article', 'damage_description', 'estimated_replacement_cost'.

        Asserted on the ROW that gets written, not on the source text that writes it:
        the checkout is submitted against a recording frappe and the appended child
        rows are read back. A fieldname rename in on_submit still fails here (the
        row would carry the wrong key), while renaming its locals or moving the
        mapping into a helper stays green. The schema half of the claim — that those
        three fieldnames really exist — lives in the meta test below.
        """
        from unittest.mock import MagicMock, patch
        from apex.habitat.doctype.housing_checkout import (
            housing_checkout as mod,
        )
        appended = []
        assessment = MagicMock()
        assessment.append.side_effect = lambda table, row: appended.append((table, row))
        stub = MagicMock()
        # Not yet checked out, so on_submit proceeds to the custody hand-off.
        stub.db.get_value.return_value = None
        stub.get_doc.side_effect = lambda *args: (
            assessment if args and isinstance(args[0], dict) else MagicMock()
        )
        doc = frappe._dict(
            name="ACC-CHKOUT-QA", assignment="ACC-ASGN-QA", bed="QA-BED",
            employee="QA-EMP", checkout_date="2026-07-01",
            custody_return_items=[
                frappe._dict(article="QA-ART-DAMAGED", return_status="Damaged"),
                frappe._dict(article="QA-ART-RETURNED", return_status="Returned"),
            ],
            add_comment=lambda *args, **kwargs: None,
        )

        # `_` is swapped for identity so the run needs no translation cache.
        with patch.object(mod, "frappe", stub), patch.object(mod, "_", lambda text: text), \
                patch.object(mod, "recalculate_spatial", lambda *args: None):
            mod.on_submit(doc)

        rows = [row for table, row in appended if table == "items"]
        self.assertEqual([r["article"] for r in rows], ["QA-ART-DAMAGED"],
                         "only Damaged/Lost custody rows become damage items")
        self.assertTrue(rows[0]["damage_description"],
                        "the damage item must carry a damage_description")
        self.assertEqual(rows[0]["estimated_replacement_cost"], 0,
                         "the draft assessment leaves the cost for the manager")

    def test_damage_assessment_doctype_has_correct_building_and_items_fields(self):
        """Custody Damage Assessment must have 'building' (required Link) and
        'items' (Table → Custody Damage Item) as expected by on_submit(), and
        Custody Damage Item must carry the three fieldnames on_submit maps onto."""
        meta = frappe.get_meta("Custody Damage Assessment")
        fieldnames = {f.fieldname: f for f in meta.fields}
        self.assertIn("building", fieldnames,
                      "'building' link field must exist on Custody Damage Assessment")
        self.assertIn("items", fieldnames,
                      "'items' table field must exist on Custody Damage Assessment")
        self.assertEqual(fieldnames["items"].options, "Custody Damage Item")

        # [#73y8nk]
        item_fieldnames = {f.fieldname for f in frappe.get_meta("Custody Damage Item").fields}
        for expected in ("article", "damage_description", "estimated_replacement_cost"):
            self.assertIn(expected, item_fieldnames,
                          f"'{expected}' must exist on Custody Damage Item")

    # [#k1ngbj]

    def _h(self):
        # [#b96xdj]
        return frappe.generate_hash(length=12).upper()

    def _fixtures(self):
        """Real, internally-consistent housing chain + a submitted assignment so a
        checkout can be created and the departure hand-off exercised end-to-end."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc({"doctype": "Site",
                               "site_name": self._h() + self._h()}).insert(ignore_permissions=True).name
        building = frappe.get_doc({"doctype": "Building", "building_name": "B " + self._h(),
                                   "site": site, "total_capacity": 4, "company": company,
                                   "default_cost_center": cc}).insert(ignore_permissions=True).name
        room = frappe.get_doc({"doctype": "Room", "naming_series": "ROOM-.####",
                               "building": building, "room_number": "R" + self._h(), "bed_capacity": 4,
                               "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        bed = frappe.get_doc({"doctype": "Bed", "naming_series": "BED-.####", "room": room,
                              "building": building, "bed_code": "B" + self._h(),
                              "status": "Available"}).insert(ignore_permissions=True).name
        project = frappe.get_doc({"doctype": "Project",
                                  "project_name": "P " + self._h()}).insert(ignore_permissions=True).name
        emp = frappe.get_doc({"doctype": "Employee", "first_name": "E " + self._h(), "company": company,
                              "gender": "Male", "date_of_birth": "1990-01-01",
                              "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        assignment = frappe.get_doc({"doctype": "Housing Assignment", "naming_series": "ACC-ASGN-.YYYY.-.####",
                                     "employee": emp, "project": project, "building": building, "room": room,
                                     "bed": bed, "cost_center": cc, "check_in_date": "2026-06-01",
                                     "assignment_type": "New Assignment"})
        assignment.submit()
        return frappe._dict(company=company, building=building, project=project, emp=emp,
                            assignment=assignment.name)

    def _checkout(self, fx, reason="Final Exit"):
        doc = frappe.get_doc({"doctype": "Housing Checkout", "naming_series": "ACC-CHKOUT-.YYYY.-.####",
                              "assignment": fx.assignment, "checkout_date": "2026-07-01",
                              "checkout_reason": reason})
        doc.submit()
        return doc

    def test_final_exit_checkout_raises_linked_departure_transport(self):
        """A Final Exit checkout produces a linked Inter-City Relocation Transport
        Request carrying the resident employee."""
        from apex.habitat.doctype.housing_checkout.housing_checkout import (
            create_departure_transport,
        )
        fx = self._fixtures()
        chk = self._checkout(fx, "Final Exit")
        tr_name = create_departure_transport(chk.name)
        self.assertTrue(tr_name)

        chk.reload()
        self.assertEqual(chk.departure_transport_request, tr_name)

        tr = frappe.get_doc("Transport Request", tr_name)
        self.assertEqual(tr.service_line, "Inter-City Relocation")
        self.assertEqual(tr.request_type, "Inter-City Relocation")
        self.assertEqual(tr.accommodation_building, fx.building)
        self.assertEqual([w.employee for w in tr.workers], [fx.emp])

    def test_departure_transport_is_idempotent(self):
        """Calling the hand-off twice returns the same request, not a duplicate."""
        from apex.habitat.doctype.housing_checkout.housing_checkout import (
            create_departure_transport,
        )
        fx = self._fixtures()
        chk = self._checkout(fx, "End of Contract")
        first = create_departure_transport(chk.name)
        second = create_departure_transport(chk.name)
        self.assertEqual(first, second)

    def test_non_departure_reason_rejected(self):
        """An Internal Transfer checkout is not a departure and must be refused."""
        from apex.habitat.doctype.housing_checkout.housing_checkout import (
            create_departure_transport,
        )
        fx = self._fixtures()
        chk = self._checkout(fx, "Internal Transfer")
        with self.assertRaises(frappe.ValidationError):
            create_departure_transport(chk.name)

    # [#q4s5ae]

    def _custody_article(self):
        category = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc(
            {"doctype": "Custody Asset Category", "category_name": "C " + self._h()}
        ).insert(ignore_permissions=True).name
        return frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "CUST-ART-.####",
            "article_name": "A " + self._h(), "category": category,
            "unit_of_measure": "Each", "standard_unit_cost": 100,
        }).insert(ignore_permissions=True).name

    def _hold(self, fx, article, qty):
        """Post an issue row on the Accommodation Stock Ledger so the employee holds
        `qty` of `article` in custody (the canonical outstanding source)."""
        frappe.get_doc({
            "doctype": "Accommodation Stock Ledger", "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-15", "item_type": "Custody Article", "item": article,
            "signed_qty": qty, "unit_cost": 100, "building": fx.building, "employee": fx.emp,
        }).insert(ignore_permissions=True)

    def _draft_checkout(self, fx, reason="End of Contract"):
        return frappe.get_doc({
            "doctype": "Housing Checkout", "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": fx.assignment, "checkout_date": "2026-07-01", "checkout_reason": reason,
        })

    def test_save_autofetches_outstanding_custody(self):
        """Saving a checkout pulls every article the resident still holds into
        custody_return_items, even though none were entered by hand."""
        fx = self._fixtures()
        article = self._custody_article()
        self._hold(fx, article, 2)
        chk = self._draft_checkout(fx)
        chk.insert(ignore_permissions=True)
        chk.reload()
        articles = {r.article for r in chk.custody_return_items}
        self.assertIn(article, articles)

    def test_autofetch_is_idempotent_and_preserves_edits(self):
        """Re-saving does not duplicate auto-fetched rows and keeps user edits."""
        fx = self._fixtures()
        article = self._custody_article()
        self._hold(fx, article, 1)
        chk = self._draft_checkout(fx)
        chk.insert(ignore_permissions=True)
        chk.custody_return_items[0].return_status = "Damaged"
        chk.save(ignore_permissions=True)
        chk.reload()
        rows = [r for r in chk.custody_return_items if r.article == article]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].return_status, "Damaged")

    def test_submit_blocked_while_custody_unresolved(self):
        """An outstanding article auto-fetched as Returned with zero qty returned is
        unresolved, so submit is blocked."""
        fx = self._fixtures()
        article = self._custody_article()
        self._hold(fx, article, 3)
        chk = self._draft_checkout(fx)
        chk.insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            chk.submit()

    def test_submit_passes_once_custody_resolved(self):
        """Falsifies the gate: resolving the item (mark Damaged) lets submit proceed,
        proving the block is driven by resolution state, not a blanket refusal."""
        fx = self._fixtures()
        article = self._custody_article()
        self._hold(fx, article, 3)
        chk = self._draft_checkout(fx)
        chk.insert(ignore_permissions=True)
        chk.custody_return_items[0].return_status = "Damaged"
        chk.submit()
        self.assertEqual(chk.docstatus, 1)

    def test_returning_full_qty_resolves_the_gate(self):
        """Marking Returned with the full outstanding quantity also clears the gate."""
        fx = self._fixtures()
        article = self._custody_article()
        self._hold(fx, article, 2)
        chk = self._draft_checkout(fx)
        chk.insert(ignore_permissions=True)
        chk.custody_return_items[0].return_status = "Returned"
        chk.custody_return_items[0].quantity_returned = 2
        chk.submit()
        self.assertEqual(chk.docstatus, 1)

    def test_damage_deduction_amount_rolls_up_child_rows(self):
        """Parent damage_deduction_amount is the server-side sum of child
        deduction_amount, not a hand-entered figure."""
        fx = self._fixtures()
        article = self._custody_article()
        self._hold(fx, article, 1)
        chk = self._draft_checkout(fx)
        chk.insert(ignore_permissions=True)
        chk.custody_return_items[0].return_status = "Damaged"
        chk.custody_return_items[0].deduction_amount = 75
        chk.damage_deduction_amount = 9999  # [#4e1lse]
        chk.save(ignore_permissions=True)
        chk.reload()
        self.assertEqual(chk.damage_deduction_amount, 75)
