# Copyright (c) 2026, AFMCO and contributors
"""Arabic-coverage guard for DocType field ``description`` prose.

A field description is body text rendered under the input, so an untranslated one
shows English under an Arabic label. ``scripts/check_translations.py`` does list
``description`` in ``JSON_TEXT_KEYS``, but ``is_candidate_text`` drops any string
over 180 characters — and a description is the one schema key that routinely runs
past that. The cap cuts both ways: a long description is invisible to MISSING, so
it can ship untranslated on a green gate, and it is equally absent from ``used``,
so translating it lands the row in STALE instead. The gate therefore cannot catch
the gap and penalises the fix, which is why this property needs its own guard.

Found via Maintenance Request ``issue_type`` (229 chars, no ar.csv row) whose
sibling ``priority`` (167 chars) was translated — the split is length, not intent.

REMAINDER is the tracked backlog: descriptions known to be untranslated when this
guard landed. It is keyed by (schema path, fieldname) rather than by the English
text so that rewording a description does not false-red the suite. The set may
only shrink; a new untranslated description fails.
"""

import csv
import glob
import json
import re

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex")

# Untranslated when this guard landed; ar.csv rows are proposed but not yet merged.
REMAINDER = {
    ("apex_core/doctype/apex_integration_settings/apex_integration_settings.json", "allowed_origins"),
    ("apex_core/doctype/apex_integration_settings/apex_integration_settings.json", "messaging_gateway_enabled"),
    ("apex_core/doctype/apex_integration_settings/apex_integration_settings.json", "messaging_gateway_url"),
    ("apex_core/doctype/apex_settings/apex_settings.json", "apex_settings_sec_retention"),
    ("apex_core/doctype/habitat_settings/habitat_settings.json", "enable_email_notifications"),
    ("apex_core/doctype/habitat_settings/habitat_settings.json", "enable_passport_mrz_ocr"),
    ("apex_core/doctype/masar_worker_token/masar_worker_token.json", "token"),
    ("apex_core/doctype/operations_alert/operations_alert.json", "alert_type"),
    ("apex_core/doctype/payment_routing_settings/payment_routing_settings.json", "target_payment_doctype"),
    ("apex_core/doctype/salary_deduction_type_rule/salary_deduction_type_rule.json", "deduction_type"),
    ("apex_core/doctype/salary_deduction_type_rule/salary_deduction_type_rule.json", "enabled"),
    ("apex_core/doctype/salary_deduction_type_rule/salary_deduction_type_rule.json", "max_percent_of_salary"),
    ("apex_core/doctype/salary_deduction_type_rule/salary_deduction_type_rule.json", "salary_component"),
    ("apex_core/doctype/salary_deduction_type_rule/salary_deduction_type_rule.json", "source_doctype"),
    ("habitat/doctype/building_license/building_license.json", "license_type"),
    ("habitat/doctype/facility_asset_movement/facility_asset_movement.json", "movement_category"),
    ("habitat/doctype/floor_plan/floor_plan.json", "room_type"),
    ("habitat/doctype/housing_checkout/housing_checkout.json", "checkout_reason"),
    ("habitat/doctype/inspection_finding_item/inspection_finding_item.json", "generated_maintenance_request"),
    ("habitat/doctype/maintenance_request/maintenance_request.json", "issue_type"),
    ("habitat/doctype/maintenance_work_order/maintenance_work_order.json", "issue_type"),
    ("habitat/doctype/resident_request/resident_request.json", "request_category"),
    ("habitat/doctype/room/room.json", "room_type"),
    ("habitat/doctype/safety_task_catalog/safety_task_catalog.json", "department"),
    ("salis/doctype/driver_portal_theme/driver_portal_theme.json", "theme"),
    ("salis/doctype/movement_cost_recovery/movement_cost_recovery.json", "needs_operations"),
    ("salis/doctype/transport_request/transport_request.json", "service_line"),
    ("salis/doctype/vehicle_damage_write_off/vehicle_damage_write_off.json", "needs_operations"),
}


def _descriptions():
    """Yield (relative schema path, fieldname, description) for every shipped DocType."""
    for path in sorted(glob.glob(f"{APP}/**/doctype/*/*.json", recursive=True)):
        try:
            payload = json.loads(open(path, encoding="utf-8").read())
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("doctype") != "DocType":
            continue
        rel = path[len(APP) + 1:]
        for field in payload.get("fields") or []:
            if not isinstance(field, dict):
                continue
            text = field.get("description")
            if isinstance(text, str) and text.strip():
                yield rel, field.get("fieldname"), text.strip()


class TestSchemaDescriptionTranslation(FrappeTestCase):
    def _ar(self):
        rows = {}
        with open(f"{APP}/translations/ar.csv", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) >= 2 and row[0].strip():
                    rows[row[0]] = row[1]
        return rows

    def test_field_descriptions_have_arabic(self):
        ar = self._ar()
        untranslated = {
            (rel, fieldname)
            for rel, fieldname, text in _descriptions()
            if not (ar.get(text) or "").strip()
        }
        new = sorted(untranslated - REMAINDER)
        self.assertEqual(
            new,
            [],
            "DocType field descriptions with no Arabic row — an Arabic user sees "
            f"English body text under an Arabic label: {new}",
        )

    def test_remainder_entries_are_still_live(self):
        """Stops the backlog rotting: a removed or renamed field must leave REMAINDER."""
        live = {(rel, fieldname) for rel, fieldname, _ in _descriptions()}
        dead = sorted(REMAINDER - live)
        self.assertEqual(
            dead, [], f"REMAINDER names descriptions that no longer exist: {dead}"
        )

    def test_descriptions_carry_no_static_placeholder(self):
        """A description renders verbatim, so an unfilled {0} would reach the user."""
        braced = sorted(
            f"{rel}:{fieldname}"
            for rel, fieldname, text in _descriptions()
            if re.search(r"\{\d+\}", text)
        )
        self.assertEqual(braced, [], f"descriptions with a format placeholder: {braced}")
