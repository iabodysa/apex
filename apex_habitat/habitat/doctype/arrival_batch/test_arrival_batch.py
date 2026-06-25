# Copyright (c) 2026, AFMCO and contributors
"""Arrival Batch tests: the pre-arrival manifest. Each case provisions its own
building, supplier, and batch so asserts are exact regardless of pre-existing
site data. Confirms the schema contract get_arrival_summary relies on
(building, expected_date, expected_count) and the Temporary Worker.arrival_batch
Link, then exercises manifest-completion telemetry end to end."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.api.arrivals_desk import get_arrival_summary


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestArrivalBatch(FrappeTestCase):
    def setUp(self):
        self.date = "2026-07-01"
        # A bare building string (not a real Accommodation Building) so the
        # assignment controller's project/cost-center gates bail early — the same
        # direct approach the sibling get_arrival_summary tests use. The Arrival
        # Batch Link is inserted with ignore_links for the same reason.
        self.building = "BLDG-" + _h()
        self.supplier = frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": "SUP-" + _h(),
            "supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
        }).insert(ignore_permissions=True, ignore_if_duplicate=True).name

    def _batch(self, rows):
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": self.building,
            "expected_date": self.date,
            "labour_supplier": self.supplier,
            "expected_workers": [{"worker_name": w, "passport_number": "P" + _h(8)} for w in rows],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        return doc

    def test_expected_count_computed_from_rows(self):
        """expected_count is derived from the manifest rows, not entered by hand."""
        doc = self._batch(["A", "B", "C"])
        self.assertEqual(doc.expected_count, 3)
        # A title is stamped for the list/link display.
        self.assertTrue(doc.title)

    def test_system_maintained_fields_are_documented_read_only(self):
        """Title, Expected Count and the row's Arrived As are derived/reconciled, not
        hand-entered: each stays read-only and carries help text saying so, so the form
        never presents them as fillable-but-broken."""
        meta = frappe.get_meta("Arrival Batch")
        for fieldname in ("title", "expected_count"):
            field = meta.get_field(fieldname)
            self.assertTrue(field.read_only, f"{fieldname} is read-only by design")
            self.assertIn("read-only by design", (field.description or "").lower())
        child = frappe.get_meta("Arrival Batch Worker").get_field("temporary_worker")
        self.assertTrue(child.read_only, "Arrived As is read-only by design")
        self.assertIn("read-only by design", (child.description or "").lower())

    def test_empty_manifest_is_rejected(self):
        """A batch with no expected workers is meaningless and must not save."""
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": self.building,
            "expected_date": self.date,
            "expected_workers": [],
        })
        self.assertRaises(frappe.ValidationError, doc.insert,
                          ignore_permissions=True, ignore_links=True)

    def test_temporary_worker_links_to_arrival_batch(self):
        """The Temporary Worker.arrival_batch field is a Link onto Arrival Batch
        (the schema half of the manifest reconciliation)."""
        meta = frappe.get_meta("Temporary Worker")
        field = meta.get_field("arrival_batch")
        self.assertIsNotNone(field, "Temporary Worker.arrival_batch exists")
        self.assertEqual(field.fieldtype, "Link")
        self.assertEqual(field.options, "Arrival Batch")

    def test_manifest_completion_measured_against_batch(self):
        """With a batch on the date and N housed arrivals, get_arrival_summary
        reports the expected count and a completion percentage (no longer None)."""
        self._batch(["A", "B", "C", "D"])  # expected 4

        # Two real housed arrivals on the date in this building.
        for _i in range(2):
            asgn = frappe.get_doc({
                "doctype": "Accommodation Assignment",
                "naming_series": "ACC-ASGN-.YYYY.-.####",
                "party_type": "Employee",
                "party": "EMP-" + _h(),
                "employee": "EMP-" + _h(),
                "building": self.building,
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
            frappe.db.set_value("Accommodation Assignment", asgn.name,
                                {"docstatus": 1, "check_in_date": self.date},
                                update_modified=False)

        r = get_arrival_summary(date=self.date, building=self.building)
        self.assertEqual(r["manifest_expected"], 4)
        self.assertEqual(r["manifest_completion_pct"], 50.0)

    def test_pending_arrival_count_drives_reconciliation_alert(self):
        """pending_arrival_count = expected minus housed (clamped at 0); this is what
        the Manifest Not Reconciled notification condition checks."""
        doc = self._batch(["A", "B", "C"])  # expected 3
        # Nothing housed yet -> all pending.
        self.assertEqual(doc.pending_arrival_count, 3)

        # House one worker on the date in this building.
        asgn = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Employee",
            "party": "EMP-" + _h(),
            "employee": "EMP-" + _h(),
            "building": self.building,
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value("Accommodation Assignment", asgn.name,
                            {"docstatus": 1, "check_in_date": self.date},
                            update_modified=False)
        self.assertEqual(doc.pending_arrival_count, 2)

    def test_arrival_notifications_are_registered(self):
        """The three arrival-lifecycle Notifications exist as standard records wired
        to the right event/document_type (the manifest condition uses the property)."""
        expected = {
            "Habitat - Arrival Batch Due Today": ("Arrival Batch", "Days Before"),
            "Habitat - Manifest Not Reconciled": ("Arrival Batch", "Days After"),
            "Habitat - Over Capacity Used": ("Accommodation Bed", "New"),
        }
        for name, (dt, event) in expected.items():
            self.assertTrue(frappe.db.exists("Notification", name), f"{name} exists")
            row = frappe.db.get_value(
                "Notification", name, ["document_type", "event", "is_standard"], as_dict=True
            )
            self.assertEqual(row.document_type, dt)
            self.assertEqual(row.event, event)
            self.assertTrue(row.is_standard)


class TestArrivalManifestWebForm(FrappeTestCase):
    """The public arrival-manifest Web Form: a labour supplier submits the expected
    workers ahead of arrival and an Arrival Batch is created from it."""

    WEB_FORM = "arrival-manifest"

    def test_web_form_is_a_published_anonymous_intake(self):
        """The Web Form targets Arrival Batch and accepts anonymous public submissions
        at the arrival-manifest route (mirrors the transport-request intake)."""
        wf = frappe.get_doc("Web Form", self.WEB_FORM)
        self.assertEqual(wf.doc_type, "Arrival Batch")
        self.assertEqual(wf.route, "arrival-manifest")
        self.assertTrue(wf.published)
        self.assertTrue(wf.anonymous)
        self.assertFalse(wf.login_required)
        self.assertTrue(wf.is_standard)

    def test_web_form_exposes_the_manifest_child_table(self):
        """The expected_workers child table is on the form so a supplier can list the
        workers; building + date are required intake fields."""
        wf = frappe.get_doc("Web Form", self.WEB_FORM)
        by_name = {f.fieldname: f for f in wf.web_form_fields}
        self.assertIn("expected_workers", by_name)
        self.assertEqual(by_name["expected_workers"].fieldtype, "Table")
        self.assertEqual(by_name["expected_workers"].options, "Arrival Batch Worker")
        self.assertTrue(by_name["building"].reqd)
        self.assertTrue(by_name["expected_date"].reqd)

    def test_accept_creates_arrival_batch_from_a_guest_submission(self):
        """Submitting the form through the native accept() path (the public, guest
        flow) creates an Arrival Batch whose expected_count is derived from the rows."""
        from frappe.website.doctype.web_form.web_form import accept

        # accept() validates Links, so use a real Accommodation Building (it only
        # requires a name) rather than the bare-string shortcut the sibling cases use.
        building = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "BLDG-" + _h(),
        }).insert(ignore_permissions=True).name
        payload = {
            "building": building,
            "expected_date": "2026-08-01",
            "expected_workers": [
                {"worker_name": "Worker " + _h(4), "passport_number": "P" + _h(8)},
                {"worker_name": "Worker " + _h(4), "passport_number": "P" + _h(8)},
            ],
        }
        doc = accept(web_form=self.WEB_FORM, data=frappe.as_json(payload))

        self.assertEqual(doc.doctype, "Arrival Batch")
        self.assertEqual(doc.building, building)
        self.assertEqual(doc.expected_count, 2)
        self.assertTrue(doc.title)
        self.assertTrue(frappe.db.exists("Arrival Batch", doc.name))
