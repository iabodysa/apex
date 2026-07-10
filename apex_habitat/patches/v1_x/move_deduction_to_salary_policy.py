# Copyright (c) 2026, AFMCO and contributors
"""Move the salary-deduction config from Habitat Settings to the Salary Deduction Policy.

The damage + housing-allowance deduction settings (gate, salary component, per-event
cap, activation date, authorizer, authorization document) were relocated off the
housing-scoped Habitat Settings single onto the law-aware Salary Deduction Policy
single (its Damage and Rent type rules). On a site that already set any of these on
Habitat Settings, those values still linger as orphan rows in ``tabSingles`` (removing
a field from a Single's JSON does not delete its stored value). This patch copies any
such value into the matching Policy type rule BEFORE the fields are gone, then deletes
the orphan rows so nothing stale remains.

Financial safety: a deduction that was ON must NOT silently turn off. If either the
damage or the housing gate was enabled, the Policy global master switch
(``enable_salary_deductions``) is turned ON so the migrated per-type rule keeps firing.

ONE-TIME, idempotent, install-safe:
  * reads the OLD values straight from ``tabSingles`` via the query builder — NOT
    ``get_single_value``, which now throws because the fields are gone from the
    Habitat Settings meta;
  * never clobbers a Policy rule an admin already configured: it only fills a rule
    value that is still empty / unset;
  * deletes the Habitat Settings orphan rows, so a second run is a pure no-op;
  * a no-op on fresh installs (no orphan rows exist).
PRUNE (remove module + the patches.txt line) once every deployed site has run it.
"""

import frappe

# [#dz3p1m]
DAMAGE_FIELDS = (
    "enable_damage_deduction",
    "damage_salary_component",
    "max_damage_deduction_per_checkout_sar",
)
RENT_FIELDS = (
    "enable_housing_allowance_deduction",
    "deduction_activation_date",
    "authorized_by",
    "authorization_document",
)
ALL_FIELDS = DAMAGE_FIELDS + RENT_FIELDS


def execute():
    try:
        if not frappe.db.exists("DocType", "Salary Deduction Policy"):
            return

        old = _read_old_values()
        if not old:
            return  # fresh install / already migrated — nothing to move

        policy = frappe.get_single("Salary Deduction Policy")

        damage_on = _truthy(old.get("enable_damage_deduction"))
        rent_on = _truthy(old.get("enable_housing_allowance_deduction"))

        if damage_on:
            rule = _ensure_rule(policy, "Damage")
            _fill_if_empty(rule, "salary_component", old.get("damage_salary_component"))
            _fill_if_empty(rule, "cap_amount_per_event", old.get("max_damage_deduction_per_checkout_sar"))
            rule.enabled = 1

        if rent_on:
            rule = _ensure_rule(policy, "Rent")
            _fill_if_empty(rule, "activation_date", old.get("deduction_activation_date"))
            _fill_if_empty(rule, "authorized_by", old.get("authorized_by"))
            _fill_if_empty(rule, "authorization_document", old.get("authorization_document"))
            rule.enabled = 1

        if damage_on or rent_on:
            # financial safety: keep the migrated deductions firing
            policy.enable_salary_deductions = 1
            policy.save(ignore_permissions=True)  # audit-ok

        # delete the Habitat Settings orphan rows so a re-run is a pure no-op
        singles = frappe.qb.Table("tabSingles")
        frappe.qb.from_(singles).delete().where(
            (singles.doctype == "Habitat Settings")
            & (singles.field.isin(list(ALL_FIELDS)))
        ).run()
        frappe.db.commit()
    except Exception:
        # [#19ji2j]
        frappe.db.rollback()
        frappe.log_error(
            title="move_deduction_to_salary_policy failed",
            message=frappe.get_traceback(),
        )


def _read_old_values():
    """Return {field: stored_value} for any Habitat Settings deduction orphan rows."""
    singles = frappe.qb.Table("tabSingles")
    rows = (
        frappe.qb.from_(singles)
        .select(singles.field, singles.value)
        .where(
            (singles.doctype == "Habitat Settings")
            & (singles.field.isin(list(ALL_FIELDS)))
        )
        .run()
    )
    return {field: value for field, value in rows}


def _truthy(value):
    return str(value) in ("1", "1.0") if value is not None else False


def _ensure_rule(policy, rule_type):
    """The policy's type rule for ``rule_type``, appending it if absent."""
    for row in policy.type_rules or []:
        if row.deduction_type == rule_type:
            return row
    return policy.append("type_rules", {"deduction_type": rule_type})


def _fill_if_empty(row, fieldname, value):
    """Set ``fieldname`` on the row only when it is still empty and a value exists."""
    if value in (None, "") :
        return
    if row.get(fieldname) in (None, ""):
        row.set(fieldname, value)
