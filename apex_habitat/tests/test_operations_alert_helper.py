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

APP = frappe.get_app_path("apex_habitat")

# Sanctioned raw-insert sites: the helper itself + the two scheduler notifiers
# that wrap their own domain-specific dedupe around the insert.
_SANCTIONED = {
    "apex_core/utils/operations_alert.py",
    "salis/tasks.py",
    "habitat/tasks.py",
}

# Matches an Operations Alert insert dict (literal name or the ALERT_DOCTYPE const).
_RAW_INSERT = re.compile(r'"doctype":\s*(?:ALERT_DOCTYPE|["\']Operations Alert["\'])')


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
