# Copyright (c) 2026, afmcoltd
"""Safety Task Catalog controller."""

from __future__ import annotations

from frappe.model.document import Document


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
        naming_series: DF.Literal["STC-.####"]
        priority: DF.Literal["High", "Medium", "Low"]
        task_code: DF.Data
        task_title: DF.Data
    pass
