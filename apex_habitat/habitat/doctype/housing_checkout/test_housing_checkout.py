# Copyright (c) 2026, AFMCO and contributors
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
        from apex_habitat.habitat.doctype.housing_checkout.housing_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": "QA-BLDG-A"})
        self.assertEqual(resolve_damage_assessment_building(assignment, None), "QA-BLDG-A")

    def test_resolve_building_assignment_wins_over_bed(self):
        # [#mv02qy]
        from apex_habitat.habitat.doctype.housing_checkout.housing_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": "QA-BLDG-A"})
        self.assertEqual(
            resolve_damage_assessment_building(assignment, "ANY-BED"), "QA-BLDG-A"
        )

    def test_resolve_building_never_empty_string(self):
        # [#pdkwyk]
        from apex_habitat.habitat.doctype.housing_checkout.housing_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": None})
        result = resolve_damage_assessment_building(assignment, "NONEXISTENT-BED")
        self.assertIsNone(result)
        self.assertNotEqual(result, "")

    def test_on_submit_locks_assignment_against_concurrent_checkout(self):
        """Regression (#4): on_submit must take a row lock on the assignment
        (for_update) and re-check check_out_date, so two concurrent checkouts for
        the same assignment serialize and the loser aborts. True concurrency is not
        reproducible single-threaded; this guards the mechanism from being removed."""
        import inspect
        from apex_habitat.habitat.doctype.housing_checkout import (
            housing_checkout as mod,
        )
        src = inspect.getsource(mod.on_submit)
        self.assertIn("for_update=True", src)
        self.assertIn("check_out_date", src)

    # [#10md08]

    def test_on_submit_uses_correct_damage_assessment_fieldnames(self):
        """on_submit() auto-creates a Custody Damage Assessment using the correct
        child-table fieldnames from the Custody Damage Item schema:
        'article', 'damage_description', 'estimated_replacement_cost_sar'.

        Verifies the field mapping is correct by inspecting the source and the
        Custody Damage Item meta — guards against future fieldname renames breaking
        the draft assessment creation.
        """
        import inspect
        from apex_habitat.habitat.doctype.housing_checkout import (
            housing_checkout as mod,
        )
        src = inspect.getsource(mod.on_submit)
        # [#ozynyi]
        self.assertIn('"article"', src, "on_submit must map 'article' to Custody Damage Item")
        self.assertIn('"damage_description"', src,
                      "on_submit must set 'damage_description' on the damage item")
        self.assertIn('"estimated_replacement_cost_sar"', src,
                      "on_submit must set 'estimated_replacement_cost_sar' on the damage item")

        # [#73y8nk]
        meta = frappe.get_meta("Custody Damage Item")
        fieldnames = {f.fieldname for f in meta.fields}
        for expected in ("article", "damage_description", "estimated_replacement_cost_sar"):
            self.assertIn(expected, fieldnames,
                          f"'{expected}' must exist on Custody Damage Item")

    def test_damage_assessment_doctype_has_correct_building_and_items_fields(self):
        """Custody Damage Assessment must have 'building' (required Link) and
        'items' (Table → Custody Damage Item) as expected by on_submit()."""
        meta = frappe.get_meta("Custody Damage Assessment")
        fieldnames = {f.fieldname: f for f in meta.fields}
        self.assertIn("building", fieldnames,
                      "'building' link field must exist on Custody Damage Assessment")
        self.assertIn("items", fieldnames,
                      "'items' table field must exist on Custody Damage Assessment")
        self.assertEqual(fieldnames["items"].options, "Custody Damage Item")

    # --- Departure transport hand-off ---

    def _h(self):
        return frappe.generate_hash(length=4).upper()

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
        from apex_habitat.habitat.doctype.housing_checkout.housing_checkout import (
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
        from apex_habitat.habitat.doctype.housing_checkout.housing_checkout import (
            create_departure_transport,
        )
        fx = self._fixtures()
        chk = self._checkout(fx, "End of Contract")
        first = create_departure_transport(chk.name)
        second = create_departure_transport(chk.name)
        self.assertEqual(first, second)

    def test_non_departure_reason_rejected(self):
        """An Internal Transfer checkout is not a departure and must be refused."""
        from apex_habitat.habitat.doctype.housing_checkout.housing_checkout import (
            create_departure_transport,
        )
        fx = self._fixtures()
        chk = self._checkout(fx, "Internal Transfer")
        with self.assertRaises(frappe.ValidationError):
            create_departure_transport(chk.name)

    # Custody auto-fetch, submit gate, and deduction roll-up.

    def _custody_article(self):
        category = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc(
            {"doctype": "Custody Asset Category", "category_name": "C " + self._h()}
        ).insert(ignore_permissions=True).name
        return frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "CUST-ART-.####",
            "article_name": "A " + self._h(), "category": category,
            "unit_of_measure": "Each", "standard_unit_cost_sar": 100,
        }).insert(ignore_permissions=True).name

    def _hold(self, fx, article, qty):
        """Post an issue row on the Accommodation Stock Ledger so the employee holds
        `qty` of `article` in custody (the canonical outstanding source)."""
        frappe.get_doc({
            "doctype": "Accommodation Stock Ledger", "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-15", "item_type": "Custody Article", "item": article,
            "signed_qty": qty, "unit_cost_sar": 100, "building": fx.building, "employee": fx.emp,
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
        chk.damage_deduction_amount = 9999  # should be overwritten by the roll-up
        chk.save(ignore_permissions=True)
        chk.reload()
        self.assertEqual(chk.damage_deduction_amount, 75)
