# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
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
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

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
        # [#18ae8f]
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
            "from_company": "Company X",
            "to_company": "Company Y",
            # [#tf8rdy]
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
        self.assertEqual(doc.is_intercompany, 1)


class TestFacilityAssetMovementOriginReconcile(FrappeTestCase):
    """from_building/from_room are reconciled to the asset's actual location: a
    hand-entered origin that contradicts the asset is rejected, and a blank origin is
    defaulted from the asset so cancel reverts to a trustworthy prior location."""

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def _building(self, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building", "building_name": name,
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        return name

    def setUp(self):
        h = self._h()
        self.b1 = self._building("ORIG-A-" + h)
        self.b2 = self._building("ORIG-B-" + h)
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset", "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Origin-QA " + h, "asset_category": "Other", "building": self.b1,
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

    def test_mismatched_from_building_rejected(self):
        """RED before fix: from_building was hand-entered and never checked, so a wrong
        origin slipped through (and on_cancel would later revert the asset to it). GREEN:
        validate throws when from_building contradicts the asset's current building."""
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": self.asset,
            "from_building": self.b2,  # [#ryzglq]
            "to_building": self.b1,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_blank_origin_defaulted_and_cancel_restores_true_prior(self):
        """A blank from_building is defaulted from the asset, so after a move and a
        cancel the asset is restored to its genuine prior building (b1), not a phantom."""
        mv = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": self.asset,
            "to_building": self.b2,  # [#ehr9h5]
        })
        mv.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(mv.from_building, self.b1)
        mv.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"), self.b2
        )
        mv.db_set("cancellation_reason", "QA origin test")
        mv.reload()
        mv.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"), self.b1
        )


class TestFacilityAssetMovementLedger(FrappeTestCase):
    """The movement ledger records each move as an immutable, queryable history
    row, instead of overwriting the asset's location in place with no trail."""

    LEDGER = "Facility Asset Movement Ledger"

    def _make_building(self, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building",
                "building_name": name,
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        return name

    def _make_asset(self, building):
        # [#69rcc5]
        doc = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Ledger-QA-Asset",
            "asset_category": "Other",
            "building": building,
        }).insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    def _make_movement(self, asset, from_b, to_b):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": asset,
            "from_building": from_b,
            "to_building": to_b,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def setUp(self):
        self.b1 = self._make_building("LEDGER-QA-A")
        self.b2 = self._make_building("LEDGER-QA-B")
        self.asset = self._make_asset(self.b1)

    def test_submit_posts_one_immutable_from_to_row(self):
        mv = self._make_movement(self.asset, self.b1, self.b2)
        rows = frappe.get_all(
            self.LEDGER,
            filters={"source_doctype": "Facility Asset Movement", "source_name": mv.name},
            fields=["name", "from_building", "to_building", "reversal_of", "is_cancelled"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].from_building, self.b1)
        self.assertEqual(rows[0].to_building, self.b2)
        self.assertFalse(rows[0].reversal_of)

        # [#3quubp]
        led = frappe.get_doc(self.LEDGER, rows[0].name)
        led.to_location = "tampered"
        with self.assertRaises(frappe.PermissionError):
            led.save(ignore_permissions=True)

    def test_post_is_idempotent(self):
        from apex.habitat.asset_movement_engine import post_asset_movement

        mv = self._make_movement(self.asset, self.b1, self.b2)
        # [#m1hdvg]
        post_asset_movement(mv)
        rows = frappe.get_all(
            self.LEDGER,
            filters={
                "source_doctype": "Facility Asset Movement",
                "source_name": mv.name,
                "reversal_of": ["is", "not set"],
            },
        )
        self.assertEqual(len(rows), 1)

    def test_cancel_posts_negated_reversal(self):
        mv = self._make_movement(self.asset, self.b1, self.b2)
        # [#1ovvcx]
        mv.db_set("cancellation_reason", "QA reversal test")
        mv.reload()
        mv.cancel()
        rows = frappe.get_all(
            self.LEDGER,
            filters={"source_doctype": "Facility Asset Movement", "source_name": mv.name},
            fields=["name", "from_building", "to_building", "reversal_of", "is_cancelled"],
        )
        self.assertEqual(len(rows), 2)
        reversal = [r for r in rows if r.reversal_of]
        self.assertEqual(len(reversal), 1)
        # [#4zl8il]
        self.assertEqual(reversal[0].from_building, self.b2)
        self.assertEqual(reversal[0].to_building, self.b1)
        self.assertTrue(reversal[0].is_cancelled)
