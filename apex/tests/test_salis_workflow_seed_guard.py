# Copyright (c) 2026, AFMCO and contributors
"""A-077 guard: every mandatory Salis native Workflow must be ACTIVE after migrate.

``salis_workflow_seed.seed_salis_workflows`` runs on every install/migrate and
creates each shipped Workflow whose target DocType exists -- a missing DocType is
its only skip condition (see ``workflow_seed_base.seed_one``). So for every
shipped, active-in-JSON definition whose ``document_type`` is installed,
``get_workflow_name(document_type)`` MUST resolve to that workflow. If the seed
silently regresses, this FAILS CI in one place, instead of each per-DocType
workflow test class merely SKIPping (the A-077 hole: a class-level ``skipUnless``
kept CI green while the inner assertions never ran).

The list is read from the seeder itself (``_WORKFLOW_DIRS`` + the shipped JSON),
so it stays the single source of truth and needs no hand-maintained copy.
"""

import frappe
from frappe.model.workflow import get_workflow_name
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.salis_workflow_seed import (
    _WORKFLOW_DIRS,
    _load_definition,
)


class TestSalisMandatoryWorkflows(FrappeTestCase):
    def test_every_shipped_active_salis_workflow_is_resolvable(self):
        """Each shipped, active Salis workflow whose DocType is installed resolves
        to its active Workflow. Mirrors the seeder's own skip rule (absent DocType)
        so it never false-fails on a partially installed module."""
        checked = 0
        for dir_name in _WORKFLOW_DIRS:
            definition = _load_definition(dir_name)
            document_type = definition["document_type"]
            # mirror seed_one: a workflow whose DocType is absent is skipped, not seeded
            if not frappe.db.exists("DocType", document_type):
                continue
            # a workflow shipped inactive by design is not mandatory-active
            if not definition.get("is_active", 1):
                continue
            workflow_name = definition.get("workflow_name", definition["name"])
            checked += 1
            self.assertEqual(
                get_workflow_name(document_type),
                workflow_name,
                f"Mandatory Salis workflow {workflow_name!r} is not active for "
                f"{document_type!r} - salis_workflow_seed regression (A-077)",
            )
            self.assertTrue(
                frappe.db.get_value("Workflow", workflow_name, "is_active"),
                f"Salis workflow {workflow_name!r} exists but is_active is falsy",
            )
        # the Salis Workflow Spine (8 DocTypes) always ships, so at least 8 resolve;
        # guards against the enumeration silently going empty (vacuous pass).
        self.assertGreaterEqual(
            checked, 8, "expected >=8 mandatory Salis workflows, enumeration looks empty"
        )
