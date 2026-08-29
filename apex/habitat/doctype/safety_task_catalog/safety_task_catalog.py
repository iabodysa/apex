# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

SOURCE_FILE_RE = re.compile(r"\S+\.(?:xlsx|xlsm|xlsb|xls|csv|ods|docx|doc)\b", re.IGNORECASE)

WORKER_FACING_FIELDS = ("task_title", "instructions")


class SafetyTaskCatalog(Document):

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from apex.habitat.doctype.safety_task_building_scope.safety_task_building_scope import SafetyTaskBuildingScope
        from frappe.types import DF

        applicable_buildings: DF.Table[SafetyTaskBuildingScope]
        applicable_to_all_buildings: DF.Check
        department: DF.Literal["Fire Safety", "Health and Hygiene", "Security", "Maintenance", "Documentation", "Awareness and Training", "Compliance and Licensing", "Emergency and Crisis"]
        evidence_required: DF.Check
        frequency: DF.Literal["Daily", "Weekly", "Monthly", "Quarterly", "Annual", "As Needed", "On Entry"]
        instructions: DF.SmallText | None
        is_active: DF.Check
        priority: DF.Literal["High", "Medium", "Low"]
        task_code: DF.Data
        task_title: DF.Data

    def validate(self):
        self.validate_source_provenance()

    def validate_source_provenance(self):
        for fieldname in WORKER_FACING_FIELDS:
            match = SOURCE_FILE_RE.search(self.get(fieldname) or "")
            if not match:
                continue
            frappe.throw(
                _(
                    "{0} carries the file it was imported from ({1}). The worker walking the round"
                    " reads this field, so write the method of inspection here or leave it empty."
                ).format(_(self.meta.get_label(fieldname)), match.group(0)),
                title=_("Import trail in an operator-facing field"),
            )
