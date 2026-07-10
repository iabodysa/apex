"""V2-B6 (P-160): field-rename wave — drop redundant prefixes, unify the
responsible-supervisor family, and strip the ``_sar`` fieldname suffix (labels
keep "(SAR)"). Council order: runs AFTER B7 (P-161) DocType renames, so every
(doctype, old, new) below names the POST-B7 DocType.

post_model_sync — ``rename_field`` needs the NEW column synced first (the on-disk
JSON already carries the new fieldname, so migrate's sync_all creates it before
this patch runs). ``rename_field`` copies the old column's value into the new one
and repoints Property Setters / Report Builder JSON / user list-settings; the
remaining reference surface (fetch_from, quoted strings, standard reports, charts,
notifications) is swept in the same commit. Registered FIRST in [post_model_sync]
so the copy lands before the v1_x backfills (assignment supervisor, salary policy)
fill any still-empty rows on the NEW fieldname.

Idempotent + guarded: ``rename_field`` is a no-op when the DocType is absent, the
new field is not in the synced meta, or (non-single) the old column no longer
exists — so fresh installs (which never had the old name) and re-runs skip safely.

posting_date -> posting_datetime is a PLAIN rename, NOT a type migration: the field
is already declared ``Datetime`` in the ledger JSON (verified), so no Date->Datetime
column conversion is needed (rename_field does not convert types).
"""

import frappe
from frappe.model.utils.rename_field import rename_field

# (doctype, old_fieldname, new_fieldname) — POST-B7 DocType names.
RENAMES = [
    # --- named prefix / clarity renames ---
    ("Lease", "supplier", "landlord"),
    ("Housing Checkout", "linked_additional_salary", "additional_salary_deduction"),
    ("Housing Inventory", "linked_facility_asset", "facility_asset"),
    ("Facility Asset Custody Assignment", "witness_role", "witness"),
    ("Facility Custody Item", "physical_condition", "condition_at_handover"),
    ("Cleaning Log", "cleaned_by", "cleaner_name"),
    ("Audit Remediation Plan", "afmco_owner", "internal_owner"),
    ("Boarding Scan Log", "worker", "employee"),
    ("Vehicle Incident", "previous_vehicle_status", "previous_status"),
    ("Route Plan", "fulfilled_by_movement", "movement_planner"),
    ("Maintenance Request", "subcontractor_dispatched", "subcontractor_service_order"),
    ("Facility Asset Movement Ledger", "moved_by", "moved_by_user"),
    ("Facility Asset Movement Ledger", "posting_date", "posting_datetime"),
    ("Idle Resident Report", "estimated_accommodation_cost_bleed_sar", "estimated_cost_bleed"),
    # --- responsible-supervisor family unification (3 names -> responsible_supervisor) ---
    ("Building", "responsible_facility_supervisor", "responsible_supervisor"),
    ("Housing Assignment", "responsible_facility_supervisor", "responsible_supervisor"),
    ("Operations Alert", "project_supervisor", "responsible_supervisor"),
    # --- _sar suffix family (drop suffix; labels retain "(SAR)") ---
    ("Employee Deduction Acknowledgment", "amount_sar", "amount"),
    ("Salary Deduction Type Rule", "cap_amount_per_event_sar", "cap_amount_per_event"),
    ("Salis Settings", "cost_recovery_ops_threshold_sar", "cost_recovery_ops_threshold"),
    ("Salis Settings", "writeoff_ops_threshold_sar", "writeoff_ops_threshold"),
    ("Accommodation Stock Ledger", "unit_cost_sar", "unit_cost"),
    ("Building License", "renewal_cost_estimate_sar", "renewal_cost_estimate"),
    ("Building", "annual_cleaning_staff_sar", "annual_cleaning_staff"),
    ("Building", "annual_cost_per_capacity_sar", "annual_cost_per_capacity"),
    ("Building", "annual_electricity_sar", "annual_electricity"),
    ("Building", "annual_other_expenses_sar", "annual_other_expenses"),
    ("Building", "annual_rent_sar", "annual_rent"),
    ("Building", "annual_supervision_sar", "annual_supervision"),
    ("Building", "annual_total_cost_sar", "annual_total_cost"),
    ("Building", "annual_water_sar", "annual_water"),
    ("Building", "monthly_cost_per_capacity_sar", "monthly_cost_per_capacity"),
    ("Custody Article", "standard_unit_cost_sar", "standard_unit_cost"),
    ("Custody Damage Assessment", "total_estimated_replacement_cost_sar", "total_estimated_replacement_cost"),
    ("Custody Damage Item", "estimated_replacement_cost_sar", "estimated_replacement_cost"),
    ("Depreciation Snapshot Item", "book_value_sar", "book_value"),
    ("Depreciation Snapshot Item", "original_cost_sar", "original_cost"),
    ("Maintenance Work Order", "total_procurement_cost_sar", "total_procurement_cost"),
    ("Operational Depreciation Snapshot", "total_book_value_sar", "total_book_value"),
    ("Subcontractor Building Coverage", "specific_rate_sar", "specific_rate"),
    ("Subcontractor Service Contract", "monthly_retainer_sar", "monthly_retainer"),
    ("Subcontractor Service Contract", "rate_per_visit_sar", "rate_per_visit"),
    ("Subcontractor Service Order", "service_cost_sar", "service_cost"),
    ("Utility Account", "average_monthly_bill_sar", "average_monthly_bill"),
    ("Utility Bill Entry", "bill_amount_sar", "bill_amount"),
    ("Utility Bill Entry", "total_bill_amount_sar", "total_bill_amount"),
    ("Salis Vehicle", "planned_daily_fuel_sar", "planned_daily_fuel"),
]


def execute():
    for doctype, old, new in RENAMES:
        if not frappe.db.exists("DocType", doctype):
            continue  # fresh cut without this DocType — nothing to rename
        meta = frappe.get_meta(doctype, cached=False)
        if not meta.get_field(new):
            continue  # new column not synced (unexpected) — skip rather than error
        if not meta.issingle and not frappe.db.has_column(doctype, old):
            continue  # fresh install / already renamed — old column gone
        rename_field(doctype, old, new)
    frappe.clear_cache()
