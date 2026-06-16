import frappe
from frappe.tests.utils import FrappeTestCase

# [#hlfy1g]
# [#rf8fpd]
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


class TestFacilityAssetMovement(FrappeTestCase):

    def test_create_valid_movement(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Facility Asset Movement", doc.name, force=True, ignore_permissions=True)

    def test_missing_facility_asset_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "to_building": "BLDG-B",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_same_from_and_to_raises(self):
        from apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-SAME",
            "to_building": "BLDG-SAME",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_intercompany_detected_in_validate_enforces_gate(self):
        # [#qsfebp]
        # [#h7lbmj]
        # [#ol3anl]
        # [#p3oz76]
        # [#9v2lzx]
        from apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
            "from_company": "Company X",
            "to_company": "Company Y",
            # [#36d9d2]
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
        self.assertEqual(doc.is_intercompany, 1)
