# Copyright (c) 2026, AFMCO and contributors
"""Refuse a Notification a ``receiver_by_role`` that cannot open the record.
THE INVARIANT -- every role named as ``receiver_by_role`` on a shipped Notification must
hold a permlevel-0, non-``if_owner`` ``read`` DocPerm on that Notification's
``document_type``.
THE DEFECT -- nothing in Frappe reconciles a notification's audience with the notified
DocType's DocPerms. ``Notification.get_list_of_recipients`` resolves the role at
``frappe/email/doctype/notification/notification.py:364-369`` via
``get_info_based_on_role(..., ignore_permissions=True)`` -- that resolver
(``frappe/core/doctype/role/role.py:90-106`` -> ``get_user_info``, :109-116) walks
Role -> ``Has Role`` -> ``User`` and nothing else; no ``has_permission`` call exists on
that path (the SMS path is identical, ``notification.py:376-394``). So the email is
delivered, on time, to exactly the named people -- and the ``/app/<doctype>/<name>``
link inside it throws ``PermissionError`` when clicked, with no signal anywhere. That is
why this is a build-time guard: the runtime is silent by construction.
EACH CLAUSE, WHY IT IS LOAD-BEARING (the colocated test re-derives the predicate with
one clause dropped and shows it goes blind on a REAL row): permlevel-0 only -- a row is
kept only when ``cint(perm.permlevel) == 0`` (``frappe/permissions.py:283-284``, filter
:289), since a permlevel-1+ row never grants the DocType, only widens FIELD access --
Finance Manager on Custody Damage Assessment held exactly that shape. Not
``if_owner``-only -- a role-targeted notification reaches non-owners too, and an
owner-scoped grant does not look like a denial (``frappe/permissions.py:297-307``
rewrites it to ``read=1``, list view still opens) while rows are filtered away per-row
(``frappe/model/db_query.py:1440``, clause at :1020-1024) and per-doc
(``frappe/permissions.py:223-228``). On that ``document_type`` specifically -- a role
may hold plenty elsewhere and none here, as HR Manager does. A child-table
``document_type`` denies everyone -- ``has_permission`` routes ``istable`` into
``has_child_permission`` before loading the meta (``frappe/permissions.py:120-121``),
which fails closed without a ``parent_doctype`` (:785-790); a notification never
supplies one. ``Administrator`` short-circuits every check
(``frappe/permissions.py:107-109``) and is excluded from judgement.
DISABLED PAIRS STAY FROZEN TOO -- ``import_file`` lists ``"Notification": ["enabled"]``
in ``ignore_values`` (``frappe/modules/import_file.py:33``, consumed :262-265): the DB's
``enabled`` overwrites disk on re-import, so a toggled-on entry stays on forever.
THE MIGRATE SKIP -- repointing a receiver in JSON is not enough: ``import_file_by_path``
skips a record whose on-disk ``modified`` is not strictly newer than the DB's
(``frappe/modules/import_file.py:143-144``, note the ``<=`` on :127); the
``migration_hash`` rescue is gated on ``doc["doctype"] == "DocType"`` (:132, applied
:139-140) and does not apply here, so every repoint needs a bumped ``modified``.
SCOPE -- STATIC ONLY -- a pure predicate over shipped JSON; imports nothing, touches no
site. The runtime half (a ``doc_events`` hook refusing a site-created Notification at
save, as ``report_role_guard`` does for Report) is a separate card obeying that
module's two constraints: never throw while ``in_migrate``/``in_install``/``in_patch``/
``in_import`` is set, and never refuse a row already stored.
"""

from __future__ import annotations

# Administrator short-circuits every permission check (frappe/permissions.py:107-109).
ALWAYS_PERMITTED = frozenset({"Administrator"})

# The predicate, one named clause per row test. Kept as a mapping rather than inlined
# into a comprehension so the colocated test can re-derive the predicate with a single
# clause DROPPED BY NAME and prove that clause load-bearing. A hand-written weakened
# copy in the test would be a second implementation free to drift from this one; this
# way the weakened variant still runs these exact clause bodies.
_CLAUSES = {
    "read": lambda row: bool(row.get("read")),
    # frappe/permissions.py:283-284 — a row above permlevel 0 never grants the DocType.
    "permlevel_0": lambda row: not int(row.get("permlevel") or 0),
    # frappe/permissions.py:297-307 — an owner-scoped grant answers only for the owner.
    "not_if_owner": lambda row: not row.get("if_owner"),
}

CLAUSE_NAMES = tuple(_CLAUSES)


def roles_that_can_open(permissions, istable, *, clauses=CLAUSE_NAMES):
    """Roles a DocType would let open one of its documents.

    ``permissions`` is any sequence of mapping-like DocPerm rows (the shipped
    DocType JSON's ``permissions`` list, or ``meta.permissions`` under a bench).
    ``clauses`` names which of ``CLAUSE_NAMES`` to apply; it exists for the
    clause-is-load-bearing proofs and every caller outside them wants the default.

    A child table returns the empty set without reading the table at all: no role
    can open one, because ``has_permission`` needs a ``parent_doctype`` a
    Notification never supplies (frappe/permissions.py:120-121, :785-790).
    """
    if istable:
        return set()
    checks = [_CLAUSES[name] for name in clauses]
    return {
        row["role"]
        for row in permissions or []
        if row.get("role") and all(check(row) for check in checks)
    }


def unreachable_pairs(pairs, doctypes, *, clauses=CLAUSE_NAMES):
    """The ``(notification, document_type, role)`` triples whose role cannot open it.

    ``pairs`` is ``[(notification_name, document_type, role, enabled)]`` — the shape
    ``apex.tests.shipped_notifications.notification_role_pairs`` returns. ``doctypes``
    maps DocType name to its shipped JSON.

    A ``document_type`` this app does not ship is NOT reported. The judgement being
    made is about a DocPerm table, and this app only owns its own: a notification over
    an ERPNext or HRMS DocType would mean grading another app's permissions, which is
    the same line ``report_role_guard._apex_owns`` draws. That is a real residual gap,
    not an oversight — see the colocated test's coverage note.
    """
    out = []
    for name, document_type, role, _enabled in pairs:
        if role in ALWAYS_PERMITTED:
            continue
        shipped = doctypes.get(document_type)
        if shipped is None:
            continue
        allowed = roles_that_can_open(
            shipped.get("permissions"), shipped.get("istable"), clauses=clauses
        )
        if role not in allowed:
            out.append((name, document_type, role))
    return sorted(out)
