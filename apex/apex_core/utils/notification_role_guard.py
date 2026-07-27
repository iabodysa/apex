# Copyright (c) 2026, AFMCO and contributors
"""A-301 — refuse a Notification a ``receiver_by_role`` that cannot open the record.

THE INVARIANT
-------------
Every role named as ``receiver_by_role`` on a shipped Notification must hold a
**permlevel-0, non-**``if_owner`` ``read`` DocPerm on that Notification's
``document_type``.

THE DEFECT IT NAMES
-------------------
Nothing in Frappe reconciles a notification's audience with the notified DocType's
DocPerms. ``Notification.get_list_of_recipients`` resolves the role at
``frappe/email/doctype/notification/notification.py:364-369`` by calling
``get_info_based_on_role(recipient.receiver_by_role, "email", ignore_permissions=True)``
— and that resolver (``frappe/core/doctype/role/role.py:90-106`` →
``get_user_info``, :109-116) walks Role → ``Has Role`` → ``User`` and nothing else.
The only filters are the role match, ``parenttype == "User"``, ``User.enabled``, and
the two demo addresses. **No** ``has_permission`` **call exists anywhere on that
path.** The SMS path is identical (``notification.py:376-394``).

So the failure is not a missing email. The email is DELIVERED, on time, to exactly
the people named — and the ``/app/<doctype>/<name>`` link inside it throws
``PermissionError`` when they click it. The receiver is told something urgent
happened and is then refused the record; there is no signal anywhere that the
notification was pointless. That is why this has to be a build-time guard: the
runtime is silent by construction.

WHY EACH CLAUSE OF THE PREDICATE
--------------------------------
Each clause below is load-bearing, and the colocated test proves it against a REAL
row, not a synthetic one, by re-deriving the predicate with that one clause removed
and showing it goes blind.

- **permlevel-0 only.** The role resolver keeps a DocPerm row only when
  ``perm.role in roles and cint(perm.permlevel) == 0``
  (``frappe/permissions.py:283-284``, applied by the filter on :289). A row at
  permlevel 1 or above never contributes to the DocType-level grant at all — it
  only widens FIELD access through ``meta.get_permlevel_access``. This clause is
  what catches a role holding a permlevel-1 row *on the very document* and still
  being unable to open it. Finance Manager on Custody Damage Assessment was exactly
  that shape.

- **not** ``if_owner``**-only.** A role-targeted notification reaches people who are
  not the record's owner, so an owner-scoped grant does not answer for them. The
  trap is that it does not look like a denial: ``frappe/permissions.py:297-307``
  rewrites an ``if_owner`` grant to ``perms[ptype] = 1 if ptype in ("select",
  "read") else 0`` — ``read`` deliberately stays 1 so the LIST view still opens.
  The rows are then filtered away per-row by ``requires_owner_constraint``
  (``frappe/model/db_query.py:1440``, clause appended at :1020-1024) and per-doc by
  the ``if_owner`` override in ``get_doc_permissions``
  (``frappe/permissions.py:223-228``). The receiver therefore opens a list, sees
  nothing, and gets no error. No shipped pair is in that state today; the clause
  exists so the guard cannot one day pass a pair that is.

- **on that** ``document_type`` **specifically.** A role may hold plenty of
  permissions elsewhere and none here. HR Manager is the live example: it holds a
  great deal in HRMS and not one row anywhere in this app.

- **a child-table** ``document_type`` **denies everyone.** ``has_permission`` routes
  an ``istable`` doctype into ``has_child_permission`` before it even loads the meta
  (``frappe/permissions.py:120-121``), and that function fails closed without a
  ``parent_doctype`` it can derive (:785-790). A notification names a document type,
  never a parent, so no role can satisfy it — the predicate returns the empty set
  rather than reading the (usually absent) permission table.

``Administrator`` is excluded from judgement: it short-circuits every check at
``frappe/permissions.py:107-109``, so it is never the role that loses access.

WHY THE BASELINE MUST FREEZE DISABLED PAIRS TOO
-----------------------------------------------
Three of the seven frozen pairs sit on notifications shipping ``enabled: 0``, and it
is tempting to scope the guard to live ones. It must not be. ``import_file`` lists
``"Notification": ["enabled"]`` in its ``ignore_values`` map
(``frappe/modules/import_file.py:33``, consumed at :262-265): on every re-import the
DB's ``enabled`` value overwrites the one on disk. A site that toggles a disabled
notification on keeps it on forever, and no migrate will ever turn it back off. A
disabled entry is one sticky toggle away from live, so it is frozen like the rest.

EDITING A SHIPPED NOTIFICATION — THE MIGRATE SKIP
--------------------------------------------------
Changing a receiver in the JSON is not enough on its own. ``import_file_by_path``
skips a record whose on-disk ``modified`` is not strictly newer than the DB's
(``frappe/modules/import_file.py:143-144``, and note the ``<=`` on :127, so an equal
timestamp also skips). The escape hatch that saves DocType — the ``migration_hash``
content compare at :139-140 — is gated on ``doc["doctype"] == "DocType"`` (:132) and
does not apply. Every notification repointed under this card therefore carries a
bumped ``modified``, or the fix would never reach a site that already has the row.

SCOPE — STATIC ONLY, DELIBERATELY
----------------------------------
This module is a pure predicate over JSON that ships in the repo; it imports nothing
and touches no site. The runtime half — a ``doc_events`` hook refusing a
site-CREATED Notification at save, the way ``report_role_guard`` does for Report —
is a separate, smaller card. If it is ever written it must obey the two constraints
that module documents: never throw while ``in_migrate`` / ``in_install`` /
``in_patch`` / ``in_import`` is set, and never refuse a row that is already stored.
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
