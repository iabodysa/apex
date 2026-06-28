# Copyright (c) 2026, AFMCO and contributors
"""Operations Alert write-path guard + helper unit test.

``insert_operations_alert`` is the one place that writes an Operations Alert.
The guard fails the build if a new raw
``frappe.get_doc({"doctype": "Operations Alert"...})`` insert appears outside the
sanctioned set, steering future engines/controllers to the helper instead of
re-pasting the system-write block.
"""

import glob
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.utils.operations_alert import insert_operations_alert
from apex_habitat.tests._helpers import _user

APP = frappe.get_app_path("apex_habitat")

# Sanctioned raw-insert sites: the helper itself + the two scheduler notifiers
# that wrap their own domain-specific dedupe around the insert.
_SANCTIONED = {
    "apex_core/utils/operations_alert.py",
    "salis/tasks.py",
    "habitat/tasks.py",
}

# Matches an Operations Alert insert dict: "doctype" as the LEADING key of a doc
# dict (the get_doc({...}).insert() shape). Anchoring to "{" + the leading key
# avoids flagging a native helper payload (e.g. assign_to.add({"assign_to": ...,
# "doctype": "Operations Alert"})) where doctype is not the dict's first key.
_RAW_INSERT = re.compile(r'\{\s*"doctype":\s*(?:ALERT_DOCTYPE|["\']Operations Alert["\'])')


class TestOperationsAlertWritePathGuard(FrappeTestCase):
    def test_no_unsanctioned_raw_inserts(self):
        offenders = []
        for f in glob.glob(f"{APP}/**/*.py", recursive=True):
            # The guard steers PRODUCTION write-paths to the helper; test fixtures
            # (under a tests/ dir or any test_*.py beside its module) legitimately
            # build raw alerts to set up analytics scenarios.
            if "/tests/" in f or os.path.basename(f).startswith("test_"):
                continue
            rel = f.split("apex_habitat/", 2)[-1]
            if rel in _SANCTIONED:
                continue
            if _RAW_INSERT.search(open(f, encoding="utf-8").read()):
                offenders.append(rel)
        self.assertEqual(
            sorted(offenders),
            [],
            "raw Operations Alert insert outside the sanctioned set "
            f"— use insert_operations_alert(): {sorted(offenders)}",
        )


class TestInsertOperationsAlert(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_inserts_open_alert_and_returns_name(self):
        name = insert_operations_alert(
            alert_type="Excessive Topup",
            severity="Critical",
            message="helper unit test alert",
        )
        self.assertTrue(name)
        self.addCleanup(frappe.delete_doc, "Operations Alert", name, force=True, ignore_permissions=True)
        doc = frappe.get_doc("Operations Alert", name)
        self.assertEqual(doc.status, "Open")
        self.assertEqual(doc.alert_type, "Excessive Topup")
        self.assertTrue(doc.raised_on)

    def test_long_message_is_clipped(self):
        name = insert_operations_alert(
            alert_type="Unsettled Rental",
            severity="Warning",
            message="x" * 5000,
        )
        self.assertTrue(name)
        self.addCleanup(frappe.delete_doc, "Operations Alert", name, force=True, ignore_permissions=True)
        self.assertLessEqual(len(frappe.db.get_value("Operations Alert", name, "message")), 2000)


class TestInsertOperationsAlertResolvesSupervisor(FrappeTestCase):
    """The shared helper must denormalise project_supervisor onto the alert, or the
    enabled Critical-alert Notification (receiver_by_document_field: project_supervisor)
    fires with an empty recipient. Proves both directions: a vehicle whose project has
    a supervisor resolves that real User; no vehicle stays None."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = frappe.db.get_value("Project", {"project_name": "OA Supervisor Probe"}, "name") or (
            frappe.get_doc({"doctype": "Project", "project_name": "OA Supervisor Probe"})
            .insert(ignore_permissions=True)
            .name
        )
        cls.sup = _user("oa_sup_probe@example.com", "Fleet Supervisor")
        if not frappe.db.exists(
            "User Permission", {"allow": "Project", "for_value": cls.project, "user": cls.sup}
        ):
            frappe.get_doc(
                {"doctype": "User Permission", "allow": "Project",
                 "for_value": cls.project, "user": cls.sup}
            ).insert(ignore_permissions=True)
        cls.vehicle = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle",
                 "plate_number": "OA-PROBE-" + frappe.generate_hash(length=4),
                 "project": cls.project}
            )
            .insert(ignore_permissions=True)
            .name
        )

    def setUp(self):
        frappe.set_user("Administrator")

    def test_supervisor_resolved_from_vehicle_project(self):
        name = insert_operations_alert(
            alert_type="Excessive Topup",
            severity="Critical",
            message="supervisor-resolution probe",
            vehicle=self.vehicle,
        )
        self.assertTrue(name)
        self.addCleanup(frappe.delete_doc, "Operations Alert", name, force=True, ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Operations Alert", name, "project_supervisor"),
            self.sup,
            "critical alert from a project-vehicle must carry that project's supervisor",
        )

    def test_no_vehicle_leaves_supervisor_empty(self):
        # Office-scoped alerts pass no vehicle; the notification condition requires
        # project_supervisor and correctly skips them — never an empty-recipient send.
        name = insert_operations_alert(
            alert_type="Unsettled Rental",
            severity="Warning",
            message="no-vehicle probe",
        )
        self.assertTrue(name)
        self.addCleanup(frappe.delete_doc, "Operations Alert", name, force=True, ignore_permissions=True)
        self.assertFalse(frappe.db.get_value("Operations Alert", name, "project_supervisor"))
