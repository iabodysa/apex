# Copyright (c) 2026, afmcoltd
"""Refuse a Notification a ``receiver_by_role`` that cannot open the record. THE INVARIANT -- every role named as ``receiver_by_role`` on a shipped Notification must hold a permlevel-0, non-``if_owner`` ``read`` DocPerm on that Notification's ``document_type``. THE DEFECT -- nothing in Frappe reconciles a notification's audience with the notified DocType's DocPerms. So the email is delivered, on time, to exactly the named people -- and the ``/app/<doctype>/<name>`` link inside it throws ``PermissionError`` when clicked, with no signal anywhere. That is why this is a build-time guard: the runtime is silent by construction. On that ``document_type`` specifically -- a role may hold plenty elsewhere and none here, as HR Manager does. SCOPE -- STATIC ONLY -- a pure predicate over shipped JSON; imports nothing, touches no site. The runtime half (a ``doc_events`` hook refusing a site-created Notification at save, as ``report_role_guard`` does for Report) is a separate card obeying that module's two constraints: never throw while ``in_migrate``/``in_install``/``in_patch``/ ``in_import`` is set, and never refuse a row already stored."""

from __future__ import annotations

ALWAYS_PERMITTED = frozenset({"Administrator"})

_CLAUSES = {
    "read": lambda row: bool(row.get("read")),
    "permlevel_0": lambda row: not int(row.get("permlevel") or 0),
    "not_if_owner": lambda row: not row.get("if_owner"),
}

CLAUSE_NAMES = tuple(_CLAUSES)


def roles_that_can_open(permissions, istable, *, clauses=CLAUSE_NAMES):
    """Roles a DocType would let open one of its documents.

    ``permissions`` is any sequence of mapping-like DocPerm rows (the shipped
    DocType JSON's ``permissions`` list, or ``meta.permissions`` under a bench).
    ``clauses`` names which of ``CLAUSE_NAMES`` to apply; it exists for the
    clause-is-load-bearing proofs and every caller outside them wants the default.
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
