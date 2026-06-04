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
