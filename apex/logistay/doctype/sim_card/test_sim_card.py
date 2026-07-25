# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests import factories

test_ignore = [
    "Company",
    "Supplier",
    "Currency",
    "Cost Center",
    "Project",
    "Item",
    "Employee",
    "Department",
]


class TestSIMCard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        factories.make_supplier("QA-TELECOM-SUPPLIER")
        cls.contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": cls.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
            }
        )
        cls.contract.insert(ignore_permissions=True, ignore_links=True)

    def _sim(self, mobile, **kw):
        doc = frappe.get_doc(
            {
                "doctype": "SIM Card",
                "naming_series": "SIM-.YYYY.-.#####",
                "company": self.company,
                "telecom_contract": self.contract.name,
                "mobile_number": mobile,
                **kw,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        return doc

    def setUp(self):
        # Per-test savepoint so a test's rollback keeps the setUpClass company /
        # contract fixtures alive: a bare rollback wiped them on the first test,
        # which is why sim_count read None and later tests lost their contract.
        frappe.db.savepoint("sim_card_test")

    def tearDown(self):
        frappe.db.rollback(save_point="sim_card_test")

    def test_no_legacy_doctypes_exist(self):
        """The design forbids a separate Mobile Number or SIM Number Assignment
        DocType; the mobile number lives on SIM Card and stays editable in place."""
        self.assertFalse(frappe.db.exists("DocType", "Mobile Number"))
        self.assertFalse(frappe.db.exists("DocType", "SIM Number Assignment"))

    def test_mobile_normalized_and_default_status(self):
        sim = self._sim("055 123-4567")
        self.assertEqual(sim.mobile_number_normalized, "0551234567")
        self.assertEqual(sim.status, "Available")
        self.assertEqual(sim.current_custodian_type, "Unassigned")

    def test_duplicate_mobile_by_layout_rejected(self):
        self._sim("0551234567")
        with self.assertRaises(frappe.ValidationError):
            self._sim("055 123 4567")  # same digits, different layout

    def test_mobile_editable_in_place_keeps_name(self):
        sim = self._sim("0559999999")
        original = sim.name
        sim.mobile_number = "0558888888"
        sim.save(ignore_permissions=True)
        self.assertEqual(sim.name, original)
        self.assertEqual(sim.mobile_number_normalized, "0558888888")

    def test_iccid_unique_when_present_but_blanks_allowed(self):
        iccid = "8996 1100 0000 0000 001"
        self._sim("0551110001", iccid=iccid)
        # Same ICCID, different separators collides (uniqueness is on a digit key).
        with self.assertRaises(frappe.ValidationError):
            self._sim("0551110002", iccid=iccid.replace(" ", "-"))
        # Two SIMs without an ICCID are both fine.
        self._sim("0551110003")
        self._sim("0551110004")

    def test_company_must_match_contract(self):
        other = factories.make_company("Other AFMCO", abbr="OAFM").name
        with self.assertRaises(frappe.ValidationError):
            self._sim("0552220001", company=other)

    def test_sim_count_tracks_contract(self):
        self._sim("0553330001")
        self._sim("0553330002")
        self.assertEqual(
            frappe.db.get_value("Telecom Contract", self.contract.name, "sim_count"), 2
        )
