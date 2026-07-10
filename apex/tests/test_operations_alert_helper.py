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

from apex.apex_core.utils.operations_alert import insert_operations_alert
from apex.tests._helpers import _user

APP = frappe.get_app_path("apex")

# [#b8m5rf]
_SANCTIONED = {
    "apex_core/utils/operations_alert.py",
    "salis/tasks/common.py",
    "habitat/tasks/maintenance.py",
    "habitat/tasks/safety.py",
}

# [#d3lmey]
_RAW_INSERT = re.compile(r'\{\s*"doctype":\s*(?:ALERT_DOCTYPE|["\']Operations Alert["\'])')


class TestOperationsAlertWritePathGuard(FrappeTestCase):
    def test_no_unsanctioned_raw_inserts(self):
        offenders = []
        for f in glob.glob(f"{APP}/**/*.py", recursive=True):
            # [#g0afuu]
            if "/tests/" in f or os.path.basename(f).startswith("test_"):
                continue
            rel = os.path.relpath(f, APP)
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
    """The shared helper must denormalise responsible_supervisor onto the alert, or the
    enabled Critical-alert Notification (receiver_by_document_field: responsible_supervisor)
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
                 "plate_number": "OA-PROBE-" + frappe.generate_hash(length=12),
                 "project": cls.project}
            )
            .insert(ignore_permissions=True)
            .name
        )

    @classmethod
    def tearDownClass(cls):
        # [#l6stgo]
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.project, "user": cls.sup})
        if frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

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
            frappe.db.get_value("Operations Alert", name, "responsible_supervisor"),
            self.sup,
            "critical alert from a project-vehicle must carry that project's supervisor",
        )

    def test_no_vehicle_leaves_supervisor_empty(self):
        # [#e6xstc]
        name = insert_operations_alert(
            alert_type="Unsettled Rental",
            severity="Warning",
            message="no-vehicle probe",
        )
        self.assertTrue(name)
        self.addCleanup(frappe.delete_doc, "Operations Alert", name, force=True, ignore_permissions=True)
        self.assertFalse(frappe.db.get_value("Operations Alert", name, "responsible_supervisor"))
