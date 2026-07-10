# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Logistay ingestion engine's batch failure handling.

Proves the per-record failure path in ``normalize_pending_intakes`` logs the
failing intake against its own record: the Error Log entry carries
``reference_doctype`` + ``reference_name`` (P-212), so an operator can open the
failing TS Intake Source straight from the log.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay import ingestion_engine


class TestIngestionEngineFailureLogging(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _pending_intake(self) -> str:
        """A minimal Pending TS Intake Source. Links/mandatory are ignored so the
        test needs no Client / Timesheet Period masters — the failure is forced
        below, so the engine never dereferences those links."""
        src = frappe.get_doc(
            {
                "doctype": ingestion_engine.INTAKE_DOCTYPE,
                "source_title": "P-212 forced-failure intake",
                "ts_client": "P212-NO-CLIENT",
                "ts_period": "P212-NO-PERIOD",
                "status": "Pending",
            }
        )
        src.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        # The engine's failure path calls frappe.db.rollback() then commits via
        # _fail_source; commit the setup row first so it survives that rollback.
        frappe.db.commit()
        return src.name

    def test_forced_failure_error_log_carries_reference(self):
        name = self._pending_intake()
        try:
            # Force a realistic per-record failure inside the batch loop.
            with patch.object(
                ingestion_engine,
                "_process_source",
                side_effect=frappe.ValidationError("forced per-record failure"),
            ):
                ingestion_engine.normalize_pending_intakes()

            logs = frappe.get_all(
                "Error Log",
                filters={
                    "reference_doctype": ingestion_engine.INTAKE_DOCTYPE,
                    "reference_name": name,
                },
                pluck="name",
            )
            self.assertTrue(
                logs,
                "Error Log entry must carry the failing intake's "
                "reference_doctype + reference_name",
            )
            # The record is also stamped Failed so it is never re-ingested.
            self.assertEqual(
                frappe.db.get_value(ingestion_engine.INTAKE_DOCTYPE, name, "status"),
                "Failed",
            )
        finally:
            frappe.db.rollback()
            for log_name in frappe.get_all(
                "Error Log", filters={"reference_name": name}, pluck="name"
            ):
                frappe.db.delete("Error Log", {"name": log_name})
            frappe.db.delete(ingestion_engine.INTAKE_DOCTYPE, {"name": name})
            frappe.db.commit()
