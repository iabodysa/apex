# Copyright (c) 2026, afmcoltd
"""Contract test for ``SubcontractorBuildingCoverage.before_save`` blocks
saving when the loaded document's doctype is not "Subcontractor Building
Coverage" — its own docstring's stated contract.

This is a child table (``istable``): the row's normal path is created and saved
as part of its parent (Subcontractor Service Contract / Building), where
``self.doctype`` is always its own name — Frappe's controller dispatch and
``BaseDocument.__init__`` set ``self.doctype`` straight from the ``doctype`` key
in the record it was built from (``frappe/model/base_document.py:130-132``), so
the mismatch branch is unreachable through the normal ``frappe.get_doc``/child
-table path. It is reachable only by instantiating the controller class directly
against a dict naming a different (real) doctype, which is what the negative
case below does.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.subcontractor_building_coverage.subcontractor_building_coverage import (
    SubcontractorBuildingCoverage,
)


class TestSubcontractorBuildingCoverageBeforeSave(FrappeTestCase):
    def test_matching_doctype_saves_without_error(self):
        doc = SubcontractorBuildingCoverage(
            {"doctype": "Subcontractor Building Coverage", "building": None, "specific_rate": 0}
        )
        # Must not raise.
        doc.before_save()

    def test_mismatched_doctype_is_blocked(self):
        doc = SubcontractorBuildingCoverage({"doctype": "Room", "building": None})
        with self.assertRaises(frappe.ValidationError) as ctx:
            doc.before_save()
        self.assertIn("DocType mismatch", str(ctx.exception))
