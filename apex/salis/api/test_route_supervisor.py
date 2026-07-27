# Copyright (c) 2026, AFMCO and contributors
"""Boot call of the Masar Route Supervisor portal (salis/api/route_supervisor.py).

A-155: ``/masar-supervisor`` mounted and then its ONLY boot call answered HTTP 417 —
Frappe's status for a ValidationError. It was not the role gate (Administrator returns
early) and not the data: the endpoint's ``frappe.get_all`` ordered by
``field(supervisor_approval,'Pending') desc``, and current frappe version-15 replaced
``validate_order_by_and_group_by``'s function BLACKLIST with an ALLOWLIST
(``ALLOWED_ORDER_BY_FUNCTIONS``, frappe/model/db_query.py). ``field`` is not on it, so
every call raised regardless of dataset or user. A bench pinned to an older frappe still
carried the blacklist, which is why the same call succeeded locally and only ever failed
against a freshly cloned version-15 — the difference was the FRAMEWORK, not the site.

The ordering itself is unchanged (Pending first, then most-recently-touched); it now
happens in Python via ``_pending_first`` over a plain ``modified desc`` query.

Three layers are pinned:
  * the boot call returns its payload on an EMPTY dataset, as Administrator and as a
    real supervisor (the exact CI condition — a bare, migrated, unseeded site);
  * ``_pending_first`` orders Pending-first and, being a stable sort, preserves the
    query's ``modified desc`` inside each group;
  * no ``order_by``/``group_by`` literal anywhere in the app calls a SQL function frappe
    does not allow — the class of bug, not just this one line.

A direct call reproduces the failure faithfully: the ValidationError is raised inside
``frappe.get_all``, so no HTTP layer is needed to trigger it.
"""

import ast
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import route_supervisor

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SORT_KWARGS = ("order_by", "group_by")
_FUNCTION_CALL = re.compile(r"\b(\w+)\s*\(")


def _allowed_sort_functions():
    """Frappe's own allowlist when the installed version exposes it, else NOTHING.

    Reading the constant instead of copying it keeps the guard in step with the
    framework; the empty fallback keeps it strict on a bench pinned to the older
    blacklist build, where an unsafe literal would otherwise pass unnoticed."""
    from frappe.model import db_query

    return set(getattr(db_query, "ALLOWED_ORDER_BY_FUNCTIONS", ()) or ())


def _sort_literals(tree):
    """(kwarg, literal) for every literal string passed as order_by/group_by."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in _SORT_KWARGS and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    yield kw.arg, kw.value.value


def _app_python_files():
    for root, dirs, files in os.walk(_APP_ROOT):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", "public"}]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


class TestRouteSupervisorBootCall(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _user_with_roles(self, email, roles):
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": email.split("@")[0],
                    "roles": [{"role": r} for r in roles],
                }
            ).insert(ignore_permissions=True)
        return email

    def _assert_payload_shape(self, res):
        for key in ("supervisor", "counts", "plans", "generated_at"):
            self.assertIn(key, res, f"boot payload must carry {key}")
        self.assertIsInstance(res["plans"], list)
        self.assertEqual(res["counts"]["total"], len(res["plans"]))
        self.assertEqual(
            res["counts"]["pending"],
            sum(1 for p in res["plans"] if p["approval"] == "Pending"),
        )

    def test_boot_call_succeeds_for_administrator(self):
        """The CI condition: Administrator on a site with no seeded plans.

        Fails before the fix with ValidationError ("Cannot use ... in order/group by"),
        which the request layer answers as HTTP 417."""
        res = route_supervisor.get_supervisor_context()
        self._assert_payload_shape(res)
        self.assertEqual(res["supervisor"]["user"], "Administrator")

    def test_boot_call_succeeds_for_a_route_supervisor_with_no_plans(self):
        """A real (non-Administrator) supervisor takes the row-scoped branch, which adds
        a route_supervisor filter and, with nothing assigned, an empty result set."""
        email = self._user_with_roles("a155-route-supervisor@test.local", ["Fleet Supervisor"])
        frappe.set_user(email)
        res = route_supervisor.get_supervisor_context()
        self._assert_payload_shape(res)
        self.assertEqual(res["supervisor"]["user"], email)
        self.assertEqual(
            [p for p in res["plans"] if p.get("name") is None],
            [],
            "a scoped read must never return a placeholder row",
        )

    def test_portal_gate_denies_a_user_without_a_supervisor_role(self):
        """The gate stays a 403 PermissionError — it was never the 417's cause."""
        email = self._user_with_roles("a155-no-portal-role@test.local", ["Internal Auditor"])
        frappe.set_user(email)
        with self.assertRaises(frappe.PermissionError):
            route_supervisor.get_supervisor_context()

    def test_pending_first_ordering_is_preserved_without_the_sql_function(self):
        """Same order the retired ``field()`` expression produced: Pending ahead of any
        decided plan, and — because the sort is stable — the query's ``modified desc``
        untouched inside each group. An unset approval counts as Pending, matching how
        the payload derives ``approval``."""
        rows = [
            {"name": "APPROVED-NEW", "supervisor_approval": "Approved"},
            {"name": "PENDING-NEW", "supervisor_approval": "Pending"},
            {"name": "REJECTED-OLD", "supervisor_approval": "Rejected"},
            {"name": "UNSET-OLD", "supervisor_approval": None},
        ]
        ordered = [p["name"] for p in route_supervisor._pending_first(rows)]
        self.assertEqual(ordered, ["PENDING-NEW", "UNSET-OLD", "APPROVED-NEW", "REJECTED-OLD"])


class TestSortClauseSafety(FrappeTestCase):
    """App-wide: an order_by/group_by literal may not call a function frappe rejects."""

    def test_no_disallowed_sql_function_in_any_sort_clause(self):
        allowed = _allowed_sort_functions()
        offenders = []
        for path in _app_python_files():
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for kwarg, literal in _sort_literals(tree):
                for func in _FUNCTION_CALL.findall(literal.lower()):
                    if func not in allowed:
                        rel = os.path.relpath(path, _APP_ROOT)
                        offenders.append(f"  apex/{rel}: {kwarg}={literal!r} calls {func}()")

        self.assertEqual(
            sorted(offenders),
            [],
            "DatabaseQuery.validate_order_by_and_group_by allows only the functions in "
            "frappe's ALLOWED_ORDER_BY_FUNCTIONS; anything else raises ValidationError, "
            "which a portal sees as HTTP 417. Sort in Python instead:\n"
            + "\n".join(sorted(offenders)),
        )

    def test_guard_actually_detects_a_disallowed_function(self):
        """Guard-of-the-guard: the scan must both find real literals and reject a bad one."""
        found = list(_sort_literals(ast.parse('frappe.get_all("X", order_by="field(a,\'b\') desc")')))
        self.assertEqual(found, [("order_by", "field(a,'b') desc")])
        self.assertNotIn("field", _allowed_sort_functions())
        scanned = sum(1 for _ in _app_python_files())
        self.assertGreater(scanned, 100, "app scan returned implausibly few python files")
