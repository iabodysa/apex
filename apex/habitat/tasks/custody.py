# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from pypika.functions import Min

_ROW_SAVEPOINT = "custody_row"
_ALERT_SAVEPOINT = "custody_alert"


def _raise_consumable_alert(message: str, dedupe_token: str) -> str | None:
    """Raise a Consumable Expired Operations Alert (idempotent), via the shared helper.

    Existence-guarded on ``(alert_type=Consumable Expired, status=Open,
    message LIKE %dedupe_token%, raised_on=today)`` so the daily job never spams a
    duplicate for the same held position. The insert itself goes through
    ``insert_operations_alert`` (the one place that writes the record). Returns the
    new alert name, or None when a duplicate was skipped or the insert failed.
    """
    from frappe.utils import today

    from apex.apex_core.utils.operations_alert import insert_operations_alert

    today_str = today()
    frappe.db.savepoint(_ALERT_SAVEPOINT)
    try:
        if frappe.db.exists(
            "Operations Alert",
            {
                "alert_type": "Consumable Expired",
                "status": "Open",
                "message": ["like", f"%{dedupe_token}%"],
                "raised_on": ["between", [f"{today_str} 00:00:00", f"{today_str} 23:59:59"]],
            },
        ):
            return None
    except Exception:
        frappe.db.rollback(save_point=_ALERT_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Consumable alert dedupe check failed ({dedupe_token})"[:140],
        )
        return None

    return insert_operations_alert("Consumable Expired", "Warning", message)


def consumable_custody_expiry_watch() -> None:
    """Flag held custody consumables past their per-article lifespan.

    A held position is a net-positive (item, employee) balance in the
    Accommodation Stock Ledger; its age is months since the EARLIEST still-held
    issue posting. Articles carry their own ``consumable_lifespan_months`` (0 = no
    expiry) so linens/mattresses age out without hardcoding a flat year. One
    bounded grouped query; the alert is one Warning per over-age position per day.
    """
    from frappe.utils import getdate, today

    sle = frappe.qb.DocType("Accommodation Stock Ledger")
    art = frappe.qb.DocType("Custody Article")
    rows = (
        frappe.qb.from_(sle)
        .inner_join(art)
        .on(art.name == sle.item)
        .select(
            sle.item.as_("article"),
            sle.employee.as_("employee"),
            Sum(sle.signed_qty).as_("net_qty"),
            Min(sle.posting_date).as_("first_held"),
            art.article_name.as_("article_name"),
            art.consumable_lifespan_months.as_("lifespan"),
        )
        .where(sle.is_cancelled == 0)
        .where(sle.item_type == "Custody Article")
        .where(sle.employee.isnotnull())
        .where(sle.employee != "")
        .where(art.consumable_lifespan_months > 0)
        .groupby(sle.item, sle.employee)
        .having(Sum(sle.signed_qty) > 0)
    ).run(as_dict=True)

    today_date = getdate(today())
    logger = frappe.logger("habitat.consumable_custody_expiry_watch")
    emp_ids = {r.employee for r in rows if r.employee}
    emp_names = (
        {
            e["name"]: e["employee_name"]
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(emp_ids)]}, fields=["name", "employee_name"]
            )
        }
        if emp_ids
        else {}
    )
    flagged = 0
    for r in rows:
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            if not r.first_held:
                continue
            held = getdate(r.first_held)
            age_months = (today_date.year - held.year) * 12 + (today_date.month - held.month)
            if today_date.day < held.day:
                age_months -= 1
            if age_months < int(r.lifespan or 0):
                continue
            emp_name = emp_names.get(r.employee) or r.employee
            token = f"{r.employee}:{r.article}"
            message = _(
                "Consumable {0} held by {1} since {2} is {3} month(s) old, past its {4}-month lifespan."
            ).format(
                r.article_name or r.article, emp_name, r.first_held, age_months, int(r.lifespan or 0)
            ) + f" [{token}]"
            if _raise_consumable_alert(message, dedupe_token=token):
                flagged += 1
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            logger.error(
                f"consumable_custody_expiry_watch row failed "
                f"(employee={r.employee}, article={r.article}): {frappe.get_traceback()}"
            )
    logger.info(
        f"consumable_custody_expiry_watch: {len(rows)} held positions scanned, {flagged} flagged"
    )


def weekly_custody_digest() -> None:
    """Email each building's responsible supervisor a weekly custody roll-up.

    Per building: open custody issues (Issued / Partially Returned), of those the
    count already past ``expected_return_date``, the SAR value still in worker
    hands (net signed ledger value, the same definition as the value-in-hands
    card), and damage assessed month-to-date. Buildings are grouped by their
    ``responsible_supervisor`` so each supervisor receives only their own
    buildings. Buildings with no supervisor, or a disabled supervisor user, are
    skipped — oversight roles already see the dashboards.

    Gated by the master email kill-switch; per-recipient delivery is isolated
    (rollback before log) so one bad recipient never aborts the rest. Idempotent:
    a re-run re-sends the current snapshot and mutates no state.
    """
    from collections import defaultdict

    from frappe.utils import date_diff, escape_html, flt, fmt_money, get_url_to_list, getdate, today

    from apex.apex_core.utils.email_gate import email_enabled, mailable

    logger = frappe.logger()

    if not email_enabled():
        logger.info("weekly_custody_digest: email disabled (Habitat Settings); skipped.")
        return

    buildings = frappe.get_all(
        "Building",
        filters={"responsible_supervisor": ["is", "set"]},
        fields=["name", "responsible_supervisor"],
    )
    if not buildings:
        logger.info("weekly_custody_digest: no building has a responsible supervisor.")
        return

    today_str = str(getdate(today()))
    month_start = str(getdate(today()).replace(day=1))

    open_counts: dict[str, int] = defaultdict(int)
    overdue_counts: dict[str, int] = defaultdict(int)
    for issue in frappe.get_all(
        "Custody Issue",
        filters={"status": ["in", ["Issued", "Partially Returned"]]},
        fields=["building", "expected_return_date"],
    ):
        if not issue.building:
            continue
        open_counts[issue.building] += 1
        if issue.expected_return_date and date_diff(today_str, issue.expected_return_date) > 0:
            overdue_counts[issue.building] += 1

    value_by_building: dict[str, float] = defaultdict(float)
    sle = frappe.qb.DocType("Accommodation Stock Ledger")
    for row in (
        frappe.qb.from_(sle)
        .select(
            sle.building,
            Coalesce(Sum(sle.signed_qty * Coalesce(sle.unit_cost, 0)), 0).as_("value"),
        )
        .where(sle.is_cancelled == 0)
        .where(sle.item_type == "Custody Article")
        .where(sle.employee.isnotnull())
        .where(sle.employee != "")
        .where(sle.building.isnotnull())
        .where(sle.building != "")
        .groupby(sle.building)
    ).run(as_dict=True):
        value_by_building[row.building] = flt(row.value)

    damage_mtd: dict[str, float] = defaultdict(float)
    cda = frappe.qb.DocType("Custody Damage Assessment")
    for row in (
        frappe.qb.from_(cda)
        .select(cda.building, Coalesce(Sum(cda.total_estimated_replacement_cost), 0).as_("cost"))
        .where(cda.docstatus == 1)
        .where(cda.assessment_date >= month_start)
        .where(cda.building.isnotnull())
        .where(cda.building != "")
        .groupby(cda.building)
    ).run(as_dict=True):
        damage_mtd[row.building] = flt(row.cost)

    by_supervisor: dict[str, list] = defaultdict(list)
    for b in buildings:
        by_supervisor[b.responsible_supervisor].append(b.name)

    list_url = get_url_to_list("Custody Issue")
    sent = 0
    for supervisor, names in by_supervisor.items():
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            if not mailable([supervisor]):
                continue
            rows = "".join(
                "<tr><td>{b}</td><td>{open_}</td><td>{overdue}</td>"
                "<td>{value}</td><td>{damage}</td></tr>".format(
                    b=escape_html(name),
                    open_=open_counts.get(name, 0),
                    overdue=overdue_counts.get(name, 0),
                    value=fmt_money(value_by_building.get(name, 0.0), currency="SAR"),
                    damage=fmt_money(damage_mtd.get(name, 0.0), currency="SAR"),
                )
                for name in names
            )
            header = "<tr><th>{b}</th><th>{o}</th><th>{ov}</th><th>{v}</th><th>{d}</th></tr>".format(
                b=_("Building"),
                o=_("Open"),
                ov=_("Overdue"),
                v=_("Value in hands"),
                d=_("Damage (MTD)"),
            )
            message = "{intro}<br><table border='1' cellpadding='4'>{header}{rows}</table><br><a href='{url}'>{cta}</a>".format(
                intro=_("Weekly custody summary for your building(s):"),
                header=header,
                rows=rows,
                url=list_url,
                cta=_("Open the custody issue list"),
            )
            frappe.sendmail(
                recipients=[supervisor],
                subject=_("Weekly Custody Digest"),
                message=message,
            )
            sent += 1
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Custody digest failed for {supervisor}"[:140],
            )

    logger.info(f"weekly_custody_digest: sent {sent} supervisor digest(s).")
