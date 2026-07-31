# Copyright (c) 2026, AFMCO and contributors
"""A-201 — refuse a Report role its ``ref_doctype`` cannot grant ``report``.

A Report's audience is its ``roles`` child table; the right to RUN it is
``frappe.has_permission(ref_doctype, "report")``, checked only when the report is
opened (``frappe/desk/query_report.py:47``). Nothing reconciles the two:
``Workspace.is_item_allowed`` clears a Report link on the roles table alone, so a role
that is named on the report but holds no ``report`` DocPerm on the ref gets a live
workspace link that throws ``PermissionError`` on click. A-189/A-200 fixed 27 such links
and ``salis/report/test_workspace_report_runnable.py`` keeps the shipped baseline empty.

That guard reads JSON off disk, so it cannot see a Report created in the DATABASE. This
hook is the runtime half. It is not a second copy of the static scan: the static scan
asks "does the app SHIP a broken link", this one asks "is this SAVE about to create a
broken audience", and only the second one sees a site-local report.

The framework itself is the main source of the defect. ``Report.set_doctype_roles``
(frappe/core/doctype/report/report.py:107-112) seeds a new non-standard report's roles
from ``[d.role for d in meta.permissions if d.permlevel == 0]`` — every permlevel-0 role,
with NO look at the ``report`` flag. It runs in ``before_insert``, i.e. before validate,
so creating a Report Builder report over an apex DocType whose DocPerms grant read but
not ``report`` produces a broken audience by default. This hook refuses that default and
names what to fix; it is deliberately not silently corrected, because dropping a role is
an access decision and the person saving is the one entitled to make it.

Why a role is refused (mirrors ``get_role_permissions``, frappe/permissions.py:283-307,
and matches ``test_workspace_report_runnable._roles_that_can_run`` clause for clause):
a permlevel above 0 never counts (:284); an ``if_owner``-only grant is rewritten back to
0 for every right outside ("select", "read") (:297-307); and a child-table ref denies
everyone, because ``has_permission`` routes an istable doctype into
``has_child_permission`` (:120), which needs a ``parent_doctype`` that query_report never
supplies. ``Administrator`` short-circuits every check (:107) and is never the offender.

MIGRATE SAFETY — the reason this can be a hook at all
-----------------------------------------------------
Shipped Report JSON is re-imported on every migrate, so a ``validate`` that fired there
would take ``bench migrate`` down on any site whose data disagrees with it. It does not
fire: ``import_doc`` sets ``doc.flags.ignore_validate = True``
(frappe/modules/import_file.py:233-237) and ``run_before_save_methods`` RETURNS on that
flag at frappe/model/document.py:1139-1140, before ``run_method("validate")`` on :1143 —
which is the only thing that composes ``doc_events`` handlers (Document.hook, :1364-1374).
``frappe.model.sync.sync_all`` reaches Report JSON through that exact path
(frappe/model/sync.py:112, ``data_import`` left False), so the module-JSON half of
"JSON creation and DB creation alike" is covered by the static guard, never by this hook.

The ``if not data_import`` on import_file.py:235 is the trap: ``sync_fixtures`` imports
through ``data_import.import_doc`` with ``data_import=True``
(frappe/core/doctype/data_import/data_import.py:289-291), so a Report delivered as a
FIXTURE by any app on the bench does run validate, in the middle of a migrate
(frappe/migrate.py:143). A patch that saves a Report is the same shape. So the flag alone
is not enough, and this hook additionally never throws while
``in_migrate``/``in_install``/``in_patch``/``in_import`` is set — it degrades to a
msgprint. A migrate cannot be aborted by this file.

The second hazard is a site that ALREADY holds a non-conforming row: throwing on save
would make an unrelated field on that report uneditable. So only roles added by THIS
save are refused. ``check_if_latest`` populates ``_doc_before_save`` (document.py:859)
before ``run_before_save_methods`` on both the insert and the update path, so the stored
role set is available here without a query. Everything else warns and saves.

APP SCOPING — ``doc_events`` on ``Report`` fires for erpnext and hrms too
------------------------------------------------------------------------
The judgement being made is about a DocPerm table, so it is made only where apex OWNS
that table: the hook no-ops unless the ``ref_doctype``'s module belongs to apex
(``frappe.local.module_app``, frappe/__init__.py:1686-1694). An hrms report over Salary
Slip and an erpnext report over Sales Invoice are untouched; a site-local Report Builder
report over ``Housing Assignment`` — the DB-creation hole — is caught. The residual gap
is an apex report over a foreign ref, which the app does not ship and which would mean
judging another app's DocPerms.

NOT COVERED, deliberately: ``Custom Role``. ``boot.get_user_pages_or_reports`` resolves a
report's audience from Custom Role FIRST (frappe/boot.py:222-233) and then EXCLUDES that
report from the roles-table query (:254), so one Custom Role row replaces a report's whole
audience without the Report doc ever being saved — this hook never sees it. That is a
separate DocType and a separate card.
"""

from __future__ import annotations

import frappe

_APP = "apex"

# Administrator short-circuits every permission check (frappe/permissions.py:107), so it
# is never the role that loses access.
_ALWAYS_PERMITTED = frozenset({"Administrator"})

# A module constant, like workflow_guard._MESSAGE; the translation extractor resolves one
# passed through _(), so this text is gated like any literal msgid. Deliberately a plain
# str: _() runs at call time inside the request, where the lang is already the reader's,
# and _lt() would return a lazy proxy with no .format for the two placeholders.
_MESSAGE = (
    "{0} does not grant {1} the Report permission, so a user holding only {1} sees this "
    "report and gets a PermissionError on opening it. Either grant report on {0} to {1} "
    "in a permlevel-0 row that is not if_owner, or remove {1} from this report's Roles."
)

_TITLE = "Report Role Cannot Run This Report"

# A migrate must never abort on data this hook did not create. in_import alone would not
# be enough: sync_fixtures imports with data_import=True, which leaves validate ON.
_MIGRATION_FLAGS = ("in_migrate", "in_install", "in_patch", "in_import")


def _roles_with_report_right(permissions, istable):
    """Roles for which ``has_permission(ref_doctype, "report")`` is True.

    ``permissions`` is any sequence of mapping-like DocPerm rows (``meta.permissions``
    under a bench, plain dicts under the colocated unit tests). Pure, so the refusal
    can be proven without a site."""
    if istable:
        return set()
    return {
        row.get("role")
        for row in permissions or []
        if row.get("role")
        and row.get("report")
        and not row.get("if_owner")
        and not int(row.get("permlevel") or 0)
    }


def denied_roles(permissions, istable, named_roles):
    """Roles named on a report that its ref_doctype would refuse ``report`` to."""
    allowed = _roles_with_report_right(permissions, istable)
    return sorted({role for role in named_roles if role} - allowed - _ALWAYS_PERMITTED)


def _named_roles(doc):
    return [row.get("role") for row in (doc.get("roles") or [])]


def _stored_roles(doc):
    """Roles already persisted on this report, so a pre-existing offender only warns."""
    previous = doc.get_doc_before_save()
    if not previous:
        return set()
    return {row.get("role") for row in (previous.get("roles") or []) if row.get("role")}


def _apex_owns(ref_doctype):
    """True only when apex ships the DocType whose DocPerms are being judged."""
    module = frappe.db.get_value("DocType", ref_doctype, "module")
    if not module:
        return False
    return frappe.local.module_app.get(frappe.scrub(module)) == _APP


def _in_migration():
    return any(frappe.flags.get(flag) for flag in _MIGRATION_FLAGS)


def validate(doc, method=None):
    """Refuse any role this report's ``ref_doctype`` cannot grant ``report``."""
    ref = doc.get("ref_doctype")
    if not ref or not _apex_owns(ref):
        return

    meta = frappe.get_meta(ref)
    offenders = denied_roles(meta.permissions, meta.istable, _named_roles(doc))
    if not offenders:
        return

    added = [role for role in offenders if role not in _stored_roles(doc)]
    if added and not _in_migration():
        frappe.throw(_message(ref, added), title=_TITLE)

    # Pre-existing rows, or any offender during a migrate: say so and let the save
    # through, so neither an unrelated edit nor a migrate is blocked by old data.
    frappe.msgprint(_message(ref, offenders), title=_TITLE, indicator="orange")


def _message(ref_doctype, roles):
    return "\n".join(frappe._(_MESSAGE).format(ref_doctype, role) for role in roles)
