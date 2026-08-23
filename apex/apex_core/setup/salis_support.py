"""Native support desk wiring for Salis, applied at install and migrate.

The holiday-list and SLA inserts pass ``ignore_permissions`` because this is installer context:
it runs as Administrator with no session user, seeding the records the support flow later reads.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.permissions import add_permission, update_permission_property
from frappe.utils import get_time, getdate

from apex.apex_core.setup.support_names import ISSUE_PRIORITIES, ISSUE_TYPES
from apex.apex_core.utils.app_owned_permissions import frappe_is_writing_its_own_records

SLA_NAME = "Salis Support SLA"
SLA_PRIORITIES = (
    ("Urgent", 3600, 14400, 0),
    ("High", 7200, 28800, 0),
    ("Medium", 14400, 86400, 1),
    ("Low", 28800, 259200, 0),
)
ISSUE_ROLE_PERMISSIONS = (
    ("Driver", {"read": 1, "create": 1, "if_owner": 1}),
    ("Fleet Manager", {"read": 1, "write": 1}),
    ("Fleet Supervisor", {"read": 1, "write": 1}),
    ("Fleet Project Manager", {"read": 1, "write": 1}),
    ("Finance Manager", {"read": 1}),
    ("Internal Auditor", {"read": 1}),
)

def _parse_workdays(value) -> list[str]:
    """The workdays the operator chose, whatever shape the wizard sent them in.

    ``frappe.parse_json`` (frappe/__init__.py:2491) handles the JSON case. The one
    thing it cannot do is accept the comma-separated string a plain text field
    produces — it raises — so the fallback below it splits by comma rather than
    failing the whole setup step over a formatting difference.
    """
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            value = frappe.parse_json(value)
        except json.JSONDecodeError:
            value = [part.strip() for part in value.split(",")]
    return [str(day).strip() for day in (value or []) if str(day).strip()]

def ensure_support_holiday_list(
    *,
    name=None,
    from_date=None,
    to_date=None,
    weekly_off=None,
    country=None,
    subdivision=None,
):
    """Resolve or create the setup calendar through ERPNext's native Holiday List.

    ``frappe.new_doc`` (frappe/__init__.py:1152) builds the Holiday List and hrms'
    own ``get_weekly_off_dates`` fills it. Nothing here re-implements a calendar:
    the one thing the primitive cannot do is decide WHICH list a Salis support SLA
    should hang off, which is the operator's answer on the wizard slide.
    """
    name = (name or "").strip()
    if not (name and from_date and to_date):
        frappe.throw(
            _(
                "Holiday List name, From Date and To Date are required to enable support SLA."
            )
        )
    if getdate(from_date) > getdate(to_date):
        frappe.throw(_("Holiday List To Date cannot be before From Date."))

    existing = frappe.db.exists("Holiday List", name)
    if existing:
        holiday_list = frappe.get_doc("Holiday List", existing)
        expected = {
            "from_date": str(getdate(from_date)),
            "to_date": str(getdate(to_date)),
            "weekly_off": weekly_off or "",
            "country": country or "",
            "subdivision": subdivision or "",
        }
        actual = {
            "from_date": str(getdate(holiday_list.from_date)),
            "to_date": str(getdate(holiday_list.to_date)),
            "weekly_off": holiday_list.weekly_off or "",
            "country": holiday_list.country or "",
            "subdivision": holiday_list.subdivision or "",
        }
        if actual != expected:
            frappe.throw(
                _(
                    "Holiday List {0} already exists with a different calendar definition."
                ).format(existing)
            )
        return existing

    holiday_list = frappe.new_doc("Holiday List")
    holiday_list.holiday_list_name = name
    holiday_list.from_date = from_date
    holiday_list.to_date = to_date
    holiday_list.weekly_off = weekly_off or None
    holiday_list.country = country or None
    holiday_list.subdivision = subdivision or None
    if weekly_off:
        holiday_list.get_weekly_off_dates()
    if country:
        holiday_list.get_local_holidays()
    holiday_list.insert(ignore_permissions=True)
    return holiday_list.name

def _sla_contract(doc):
    priorities = {
        (
            row.priority,
            int(row.response_time or 0),
            int(row.resolution_time or 0),
            int(row.default_priority or 0),
        )
        for row in doc.priorities
    }
    schedule = {
        (
            row.workday,
            str(get_time(row.start_time)),
            str(get_time(row.end_time)),
        )
        for row in doc.support_and_resolution
    }
    fulfilled = {row.status for row in doc.sla_fulfilled_on}
    return priorities, schedule, fulfilled

def _validate_existing_sla(doc, holiday_list, workdays, start_time, end_time):
    priorities, schedule, fulfilled = _sla_contract(doc)
    expected_schedule = {
        (day, str(get_time(start_time)), str(get_time(end_time))) for day in workdays
    }
    compatible = (
        doc.service_level == SLA_NAME
        and bool(doc.enabled)
        and doc.document_type == "Issue"
        and bool(doc.default_service_level_agreement)
        and bool(doc.apply_sla_for_resolution)
        and doc.default_priority == "Medium"
        and doc.holiday_list == holiday_list
        and not getattr(doc, "entity_type", None)
        and not getattr(doc, "entity", None)
        and not getattr(doc, "condition", None)
        and not getattr(doc, "start_date", None)
        and not getattr(doc, "end_date", None)
        and not getattr(doc, "pause_sla_on", None)
        and priorities == set(SLA_PRIORITIES)
        and schedule == expected_schedule
        and fulfilled == {"Resolved", "Closed"}
    )
    if not compatible:
        frappe.throw(
            _(
                "Service Level Agreement {0} already exists with an incompatible contract."
            ).format(doc.name)
        )

def configure_support_sla(
    *, enabled=False, holiday_list=None, workdays=None, start_time=None, end_time=None
):
    """Create the native Issue SLA only after the operator supplies its site schedule.

    The SLA is a native Service Level Agreement built with ``frappe.new_doc``
    (frappe/__init__.py:1152); the switch is written with ``frappe.db.set_single_value``
    (frappe/database/database.py:782) rather than by loading the Single, so enabling
    support does not re-run that settings document's validation mid-wizard.

    Refuses loudly when the schedule is incomplete: an SLA with no workdays and no
    hours accepts every ticket and promises nothing, which reads as configured.
    """
    if not enabled:
        return None
    workdays = _parse_workdays(workdays)
    if not (holiday_list and workdays and start_time and end_time):
        frappe.throw(
            _(
                "Holiday List, workdays, support start time and support end time are required "
                "to enable the Salis support SLA."
            )
        )
    if not frappe.db.exists("Holiday List", holiday_list):
        frappe.throw(_("Holiday List {0} does not exist.").format(holiday_list))
    existing = frappe.db.exists("Service Level Agreement", {"service_level": SLA_NAME})
    if existing:
        doc = frappe.get_doc("Service Level Agreement", existing)
        _validate_existing_sla(doc, holiday_list, workdays, start_time, end_time)
        frappe.db.set_single_value(
            "Support Settings", "track_service_level_agreement", 1
        )
        return doc.name

    missing_priorities = [
        priority
        for priority, _response, _resolution, _is_default in SLA_PRIORITIES
        if not frappe.db.exists("Issue Priority", priority)
    ]
    if missing_priorities:
        frappe.throw(
            _("Required Issue Priorities are missing: {0}.").format(
                ", ".join(missing_priorities)
            )
        )

    doc = frappe.new_doc("Service Level Agreement")
    doc.service_level = SLA_NAME
    doc.document_type = "Issue"
    doc.default_service_level_agreement = 1
    doc.enabled = 1
    doc.apply_sla_for_resolution = 1
    doc.holiday_list = holiday_list
    for priority, response, resolution, is_default in SLA_PRIORITIES:
        doc.append(
            "priorities",
            {
                "priority": priority,
                "response_time": response,
                "resolution_time": resolution,
                "default_priority": is_default,
            },
        )
    for day in workdays:
        doc.append(
            "support_and_resolution",
            {"workday": day, "start_time": start_time, "end_time": end_time},
        )
    for status in ("Resolved", "Closed"):
        doc.append("sla_fulfilled_on", {"status": status})
    frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
    doc.insert(ignore_permissions=True)
    return doc.name

def refuse_shipped_issue_type_edit(doc, method=None, *args, **kwargs):
    """Refuse renaming or editing an issue type the app ships.

    ``Issue Type`` carries ``allow_rename: 1`` and its only field is ``description``, and
    the fixture is reimported with ``force=True``, which deletes the row and re-inserts it
    from a file that carries no description. So an annotation is wiped on the next migrate
    and a rename leaves the shipped name recreated beside the renamed one. Both are silent.

    Only the six shipped names are covered; an operator's own type is untouched. An Arabic
    label belongs in the translation file, which is why renaming is refused rather than
    accommodated.
    """
    _refuse_if_shipped(doc, _("renamed or edited"), ISSUE_TYPES, _("issue type"))


def refuse_shipped_issue_priority_deletion(doc, method=None):
    """Refuse deleting a priority the app ships, because the next update restores it.

    ``apex/fixtures/issue_priority.json`` travels the same ``force=True`` reimport as the
    issue types three lines above it in the hooks list, so a deleted priority comes back
    with nothing said. ``SLA_PRIORITIES`` names all four in the support contract this app
    builds, so removing one also leaves that contract naming a priority that is gone until
    the next migrate puts it back.

    Only the four shipped names are covered; a priority the operator adds is untouched.
    """
    _refuse_if_shipped(doc, _("deleted"), ISSUE_PRIORITIES, _("issue priority"))


def refuse_shipped_issue_type_deletion(doc, method=None):
    """Refuse deleting an issue type the app ships, because the next update restores it.

    ``apex/fixtures/issue_type.json`` is reimported with ``force=True`` on every migrate
    (data_import.py:288, and import_file.py:130 puts the skip gate behind ``if not
    force``), so a deleted shipped type comes back with nothing said. ERPNext grants
    Issue Type write to Support Team as well as System Manager, so an operator can make
    that deletion, work on the assumption it held, and find the type back after an
    update.

    Only deletion of a SHIPPED name is refused. An added type is not in the file, so the
    reimport never touches it and it survives — there is no surprise to prevent there.

    Stands down while Frappe is installing, migrating or patching, so the fixture's own
    import still lands.
    """
    _refuse_if_shipped(doc, _("deleted"), ISSUE_TYPES, _("issue type"))


def _refuse_if_shipped(doc, attempted_action, shipped_names, family):
    """Throw when ``doc`` is one the app ships and a person, not Frappe, is writing it."""
    if doc.name not in shipped_names:
        return
    if frappe_is_writing_its_own_records():
        return
    frappe.throw(
        _(
            "{0} is an {1} Apex ships, and every update puts it back as the app defines"
            " it. It cannot be {2} here. Ask for the change to ship with the app."
        ).format(_(doc.name), family, attempted_action),
        frappe.PermissionError,
        title=_("Set by Apex"),
    )


def grant_issue_role_permissions():
    """Create missing native Custom DocPerm rows without rewriting operator-owned rows."""
    if not frappe.db.exists("DocType", "Issue"):
        return
    for role, flags in ISSUE_ROLE_PERMISSIONS:
        if not frappe.db.exists("Role", role):
            continue
        if frappe.db.exists(
            "Custom DocPerm", {"parent": "Issue", "role": role, "permlevel": 0}
        ):
            continue
        add_permission("Issue", role, ptype="read", permlevel=0)
        for permission_type, value in flags.items():
            update_permission_property("Issue", role, 0, permission_type, value)
