import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
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


class TestAccommodationCheckout(FrappeTestCase):

    def test_create_valid_checkout(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_date": "2026-07-01",
            "checkout_reason": "End of Contract",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.checkout_reason, "End of Contract")
        frappe.delete_doc("Accommodation Checkout", doc.name, force=True, ignore_permissions=True)

    def test_missing_assignment_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "checkout_date": "2026-07-01",
            "checkout_reason": "Final Exit",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_checkout_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_reason": "Final Exit",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    # --- resolve_damage_assessment_building (bug #2) ---------------------------
    # The auto-created Custody Damage Assessment has a MANDATORY Building link, so
    # the building must come from the authoritative submitted assignment and must
    # never collapse to "" (an empty Link fails the mandatory field and the draft
    # assessment is then silently dropped by the best-effort try/except).

    def test_resolve_building_prefers_assignment(self):
        from apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": "QA-BLDG-A"})
        self.assertEqual(resolve_damage_assessment_building(assignment, None), "QA-BLDG-A")

    def test_resolve_building_assignment_wins_over_bed(self):
        # Assignment building present → the bed is never consulted (precedence).
        from apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout import (
            resolve_damage_assessment_building,
        )
        assignment = frappe._dict({"building": "QA-BLDG-A"})
        self.assertEqual(
            resolve_damage_assessment_building(assignment, "ANY-BED"), "QA-BLDG-A"
        )

    def test_resolve_building_never_empty_string(self):
        # Regression: with no building anywhere, return None — NOT "".
        from apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout import (
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
        from apex_habitat.habitat.doctype.accommodation_checkout import (
            accommodation_checkout as mod,
        )
        src = inspect.getsource(mod.on_submit)
        self.assertIn("for_update=True", src)
        self.assertIn("check_out_date", src)

    # --- P16 checkout → damage assessment fieldname verification ---------------

    def test_on_submit_uses_correct_damage_assessment_fieldnames(self):
        """on_submit() auto-creates a Custody Damage Assessment using the correct
        child-table fieldnames from the Custody Damage Item schema:
        'article', 'damage_description', 'estimated_replacement_cost_sar'.

        Verifies the field mapping is correct by inspecting the source and the
        Custody Damage Item meta — guards against future fieldname renames breaking
        the draft assessment creation.
        """
        import inspect
        from apex_habitat.habitat.doctype.accommodation_checkout import (
            accommodation_checkout as mod,
        )
        src = inspect.getsource(mod.on_submit)
        # Must use the correct schema fieldnames when building the damage item row
        self.assertIn('"article"', src, "on_submit must map 'article' to Custody Damage Item")
        self.assertIn('"damage_description"', src,
                      "on_submit must set 'damage_description' on the damage item")
        self.assertIn('"estimated_replacement_cost_sar"', src,
                      "on_submit must set 'estimated_replacement_cost_sar' on the damage item")

        # Also confirm these fieldnames are in the actual Custody Damage Item schema
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
