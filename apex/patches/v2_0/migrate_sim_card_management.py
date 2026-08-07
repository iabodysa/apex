# Copyright (c) 2026, AFMCO and contributors
"""Migrate legacy site-level SIM records into the Logistay SIM DocTypes.

The legacy data lives in a SITE-LEVEL custom DocType (created per site, not shipped
in this app), so its exact name and field set are unknown here. This patch resolves
both defensively: it finds the source DocType from a candidate list and maps each
logical field (mobile, iccid, supplier, company, employee, project, cost center)
through a per-field synonym list against the source meta. Nothing is guessed:

  * migratable  -> a normalizable mobile number AND a resolvable company + supplier,
  * ambiguous   -> a mobile but a missing company/supplier: QUARANTINED for review,
                   never invented,
  * rejected    -> no usable mobile number: skipped.

It is idempotent: a SIM whose normalized mobile already exists is skipped, the
per-(company, supplier) migration contract is reused, and a SIM that already has a
submitted custody event is not re-opened. After a real run the source DocType is
set read-only so the legacy screen freezes until reconciliation is accepted.

``dry_run()`` reports the exact source / migratable / ambiguous / rejected counts
(and the quarantined rows) without writing anything — run it via
``bench execute apex.patches.v2_0.migrate_sim_card_management.dry_run``.
"""

from __future__ import annotations

import frappe

from apex.logistay.utils.normalize import normalize_msisdn

SOURCE_CANDIDATES = [
    "SIM Card Management",
    "SIM Management",
    "SIM Card Register",
    "SIM Register",
    "SIM Inventory",
    "Mobile SIM",
]

FIELD_SYNONYMS = {
    "mobile": ["mobile_number", "mobile_no", "mobile", "phone", "phone_number", "number", "msisdn", "sim_number", "line_number"],
    "iccid": ["iccid", "icc_id", "sim_serial", "serial_number", "serial"],
    "supplier": ["supplier", "provider", "operator", "telecom_provider", "carrier", "vendor", "network"],
    "company": ["company"],
    "employee": ["employee", "assigned_to", "assigned_employee", "holder", "custodian", "user"],
    "project": ["project"],
    "cost_center": ["cost_center", "costcenter"],
    "plan": ["plan", "plan_name", "package", "bundle"],
    "start_date": ["start_date", "activation_date", "issue_date", "from_date"],
    "end_date": ["end_date", "expiry_date", "expiry", "to_date"],
}

MIGRATION_REFERENCE = "MIGRATED"


def source_doctype():
    for name in SOURCE_CANDIDATES:
        if frappe.db.exists("DocType", name):
            return name
    return None


def _field_map(meta):
    """Resolve each logical field to a real source column (or None)."""
    return {
        logical: next((c for c in candidates if meta.has_field(c)), None)
        for logical, candidates in FIELD_SYNONYMS.items()
    }


def _classify(row, fmap):
    """Return (kind, mobile_norm, company, supplier). kind is
    migratable / ambiguous / rejected."""
    raw_mobile = row.get(fmap["mobile"]) if fmap["mobile"] else None
    mobile = normalize_msisdn(raw_mobile)
    if not mobile:
        return "rejected", None, None, None
    company = row.get(fmap["company"]) if fmap["company"] else None
    supplier = row.get(fmap["supplier"]) if fmap["supplier"] else None
    if supplier and not frappe.db.exists("Supplier", supplier):
        supplier = None
    if not company or not supplier:
        return "ambiguous", mobile, company, supplier
    return "migratable", mobile, company, supplier


def _scan():
    """Read the source rows and bucket them. Returns (fmap, buckets)."""
    source = source_doctype()
    buckets = {"source": source, "migratable": [], "ambiguous": [], "rejected": []}
    if not source:
        return None, buckets
    meta = frappe.get_meta(source)
    fmap = _field_map(meta)
    fields = ["name"] + [c for c in fmap.values() if c]
    for row in frappe.get_all(source, fields=list(dict.fromkeys(fields)), limit_page_length=0):
        kind, mobile, company, supplier = _classify(row, fmap)
        buckets[kind].append(
            {"name": row.get("name"), "mobile": mobile, "company": company, "supplier": supplier, "row": row}
        )
    return fmap, buckets


def dry_run():
    """Report counts and quarantined rows without writing anything."""
    fmap, buckets = _scan()
    summary = {
        "source_doctype": buckets["source"],
        "field_map": fmap,
        "source": sum(len(buckets[k]) for k in ("migratable", "ambiguous", "rejected")),
        "migratable": len(buckets["migratable"]),
        "ambiguous": len(buckets["ambiguous"]),
        "rejected": len(buckets["rejected"]),
        "quarantined_rows": [r["name"] for r in buckets["ambiguous"]],
    }
    frappe.logger().info(f"SIM migration dry run: {summary}")
    return summary


def _migration_contract(company, supplier, row, fmap):
    """Reuse-or-create the submitted per-(company, supplier) migration contract."""
    existing = frappe.db.get_value(
        "Telecom Contract",
        {"company": company, "supplier": supplier, "contract_reference": MIGRATION_REFERENCE, "docstatus": 1},
        "name",
    )
    if existing:
        return existing
    start = (row.get(fmap["start_date"]) if fmap["start_date"] else None) or frappe.utils.today()
    end = (row.get(fmap["end_date"]) if fmap["end_date"] else None) or frappe.utils.add_days(start, 365)
    if frappe.utils.getdate(end) < frappe.utils.getdate(start):
        end = frappe.utils.add_days(start, 365)
    currency = frappe.get_cached_value("Company", company, "default_currency") or "SAR"
    contract = frappe.get_doc(
        {
            "doctype": "Telecom Contract",
            "company": company,
            "supplier": supplier,
            "contract_reference": MIGRATION_REFERENCE,
            "contract_start_date": start,
            "contract_end_date": end,
            "billing_frequency": "Monthly",
            "recurring_amount": 0,
            "currency": currency,
            "notes": "Auto-created during SIM Card Management migration. Review and complete billing details.",
        }
    )
    contract.insert(ignore_permissions=True)  # audit-ok — data migration, no user session
    contract.submit()
    return contract.name


def _migrate_row(entry, fmap):
    """Create the SIM (and opening custody) for one migratable row. Idempotent."""
    mobile = entry["mobile"]
    if frappe.db.exists("SIM Card", {"mobile_number_normalized": mobile}):
        return "skipped"

    row = entry["row"]
    contract = _migration_contract(entry["company"], entry["supplier"], row, fmap)
    sim = frappe.get_doc(
        {
            "doctype": "SIM Card",
            "company": entry["company"],
            "telecom_contract": contract,
            "mobile_number": row.get(fmap["mobile"]),
            "iccid": row.get(fmap["iccid"]) if fmap["iccid"] else None,
            "plan_name": row.get(fmap["plan"]) if fmap["plan"] else None,
        }
    )
    sim.insert(ignore_permissions=True)  # audit-ok — data migration, no user session

    employee = row.get(fmap["employee"]) if fmap["employee"] else None
    if employee and frappe.db.exists("Employee", employee):
        emp_company = frappe.db.get_value("Employee", employee, "company")
        if emp_company == entry["company"] and not frappe.db.exists(
            "SIM Custody Assignment", {"sim_card": sim.name, "docstatus": 1}
        ):
            assignment = frappe.get_doc(
                {
                    "doctype": "SIM Custody Assignment",
                    "company": entry["company"],
                    "sim_card": sim.name,
                    "action": "Assign",
                    "assignment_date": frappe.utils.today(),
                    "custodian_type": "Employee",
                    "employee": employee,
                    "reason": "Opening custody migrated from SIM Card Management.",
                }
            )
            assignment.insert(ignore_permissions=True)  # audit-ok — data migration, no user session
            assignment.submit()
    return "migrated"


def execute():
    fmap, buckets = _scan()
    if not buckets["source"]:
        return

    migrated = skipped = 0
    for entry in buckets["migratable"]:
        frappe.db.savepoint("sim_row")
        try:
            result = _migrate_row(entry, fmap)
        except Exception:
            frappe.db.rollback(save_point="sim_row")
            frappe.log_error(
                title="SIM migration row failed",
                message=f"{buckets['source']} {entry['name']}\n{frappe.get_traceback()}",
            )
        else:
            migrated += result == "migrated"
            skipped += result == "skipped"

    if buckets["ambiguous"]:
        frappe.logger().info(
            "SIM migration quarantined %s ambiguous rows for review: %s"
            % (len(buckets["ambiguous"]), [r["name"] for r in buckets["ambiguous"]])
        )

    if migrated:
        try:
            frappe.db.set_value("DocType", buckets["source"], "read_only", 1)
        except Exception:
            frappe.log_error(title="SIM migration: could not set source read-only")

    frappe.logger().info(
        "SIM migration: migrated=%s skipped=%s ambiguous=%s rejected=%s"
        % (migrated, skipped, len(buckets["ambiguous"]), len(buckets["rejected"]))
    )

    _refuse_to_be_stamped_over_nothing(len(buckets["migratable"]), migrated + skipped)


def _refuse_to_be_stamped_over_nothing(attempted: int, completed: int) -> None:
    """Raise when not one migratable row got through.

    The per-row savepoint above is deliberate: one unusable row must not strand a
    whole migrate, so a partial run finishes and is stamped. But returning normally
    when EVERY row failed hands Patch Log a success over data that never moved, and
    the patch never runs again — the legacy records stay in the legacy DocType with
    nothing left to migrate them. Raising here is what makes bench migrate exit
    non-zero and leaves the patch unstamped so a fixed run can retry it."""
    if attempted and not completed:
        frappe.throw(
            f"SIM migration moved 0 of {attempted} migratable rows; every row failed "
            "and the legacy records are untouched. See the 'SIM migration row failed' "
            "Error Log entries, fix the cause, and run bench migrate again."
        )
