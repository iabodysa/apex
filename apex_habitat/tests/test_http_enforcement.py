"""Regression test: HTTP-method enforcement (#33).

File-level test — no Frappe site needed. Uses ast and stdlib only.

Policy: any @frappe.whitelist() endpoint that performs a write operation
(insert, save, delete, db_set, db_insert, submit, cancel, set_value) MUST
declare methods=["POST"] in the decorator.

A bare @frappe.whitelist() (without methods=) accepts GET and POST equally,
which means write side-effects can be triggered via a cacheable GET request —
a CSRF and cache-poisoning risk.
"""

import ast
import glob
import os
import unittest

APP_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..")
)

# [#21zdiy]
WRITE_CALLS = {
    "insert",
    "save",
    "submit",
    "cancel",
    "delete",
    "delete_doc",
    "db_set",
    "db_insert",
    "db_update",
    "set_value",
    "db_delete",
    "rename_doc",
}

# [#tnlcz2]
SAFE_ALLOWLIST = [
    (
        "salis/api/boarding_flow.py",
        "get_trip_boarding",
        "Driver panel READ. The only write is a read-time _apply_auto_confirm save "
        "that realises an already-elapsed worker-claim timeout (a system timeout, "
        "not a client-driven write); it bumps no notify quota and publishes nothing. "
        "Safe under GET.",
    ),
    (
        "salis/api/boarding_flow.py",
        "worker_trip_boarding",
        "Worker boarding poll READ. The only write is the same read-time "
        "_apply_auto_confirm save (system timeout realisation); the endpoint returns "
        "the worker's own state and writes no client-driven data. Safe under GET.",
    ),
]


# [#68gsyt]
PERMISSION_CALLS = {"has_permission", "check_permission"}

# [#dha1uj]
PERMISSION_RECHECK_ALLOWLIST = [
    (
        "habitat/web_form/accommodation_resident_request/accommodation_resident_request.py",
        "submit_resident_request",
        "Public QR intake. allow_guest; authorisation is the location token plus "
        "a honeypot + per-IP rate limit. A Guest has no role to permission-check.",
    ),
    (
        "salis/web_form/transport_request/transport_request.py",
        "submit_transport_request",
        "Public transport-request intake. allow_guest; token/honeypot/rate-limit "
        "guarded. A Guest has no role to permission-check.",
    ),
    (
        "salis/api/masar.py",
        "create_worker_request",
        "Masar guest endpoint. allow_guest; authorisation is the Masar worker "
        "token resolved server-side, not a desk permission.",
    ),
    (
        "salis/api/masar.py",
        "create_worker_transport_request",
        "Masar guest endpoint. allow_guest; the worker is resolved server-side from "
        "the token (_resolve_worker) and is the sole identity for the request — the "
        "client never supplies a worker id; explicit rate_limit. A Guest has no role "
        "to permission-check.",
    ),
    (
        "salis/api/masar.py",
        "notify_hr_iqama_expiring",
        "Masar guest endpoint. allow_guest; authorisation is the Masar worker "
        "token resolved server-side (_resolve_worker), scope derived server-side, "
        "explicit rate_limit. A Guest has no role to permission-check.",
    ),
    (
        "salis/api/boarding.py",
        "scan_boarding_pass",
        "Boarding scan endpoint. Authorisation is an HMAC-signed pass token "
        "(signature + TTL + trip-manifest verified) bound to (trip, worker), not a "
        "desk permission; every outcome is logged to Boarding Scan Log. "
        "Token-resolved writer.",
    ),
    (
        "salis/api/masar.py",
        "confirm_boarding",
        "Masar guest endpoint. allow_guest; authorisation is the Masar worker "
        "token resolved server-side (_resolve_worker), scope derived from the "
        "worker's own trip manifest, explicit rate_limit. A Guest has no role to "
        "permission-check.",
    ),
    (
        "salis/api/driver_portal.py",
        "submit_fuel_request",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side (never client-supplied) and the vehicle must be bound to "
        "that driver (raises PermissionError otherwise); the document is stamped "
        "with the caller's own identity. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "raise_support_ticket",
        "Driver portal. The Salis Driver and raised_by are resolved from the "
        "session server-side; the Issue is stamped with the caller's own "
        "identity. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "driver_check_in",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side (_resolve_driver); the Driver Attendance is the caller's "
        "own (today's) record, inserted/submitted via _persist_attendance with "
        "ignore_permissions (audit-ok — session identity). Token/identity writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "driver_check_out",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side (_resolve_driver); updates the caller's own (today's) "
        "Driver Attendance via _persist_attendance with ignore_permissions "
        "(audit-ok — session identity). Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "reply_to_ticket",
        "Driver portal. The Issue is resolved through _driver_issue, scoped to "
        "the session driver's own custom_driver, so a driver can only reply on "
        "their own ticket; the Communication is stamped with the caller's own "
        "identity. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "report_vehicle_problem",
        "Driver portal. The Salis Driver and bound vehicle are resolved from the "
        "session server-side; delegates to raise_support_ticket internals which "
        "stamp the caller's own identity. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "request_license_renewal",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side; refuses unless the caller's own licence is within the "
        "renewal window; delegates to raise_support_ticket internals stamped with "
        "the caller's identity. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "start_my_trip",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); the Trip Start Log is the caller's "
        "own record. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "complete_my_trip",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); updates the caller's own Trip Start "
        "Log. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "manual_board_workers",
        "Driver portal. The Salis Driver is resolved from the session server-side "
        "and the trip is honoured only when it belongs to that driver "
        "(boarding._resolve_trip raises PermissionError otherwise); only workers on "
        "the trip's own manifest are boarded and every attempt is logged to Boarding "
        "Scan Log. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "mark_stop_progress",
        "Driver portal. The Salis Driver is resolved from the session server-side "
        "and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); the Trip Stop Progress row is written "
        "on the caller's own open Trip Start Log. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "save_push_subscription",
        "Driver portal. The Salis Driver is resolved from the session server-side "
        "(_resolve_driver, never client-supplied); the Driver Push Subscription is "
        "bound to the caller's own driver/user and saved with ignore_permissions "
        "(audit-ok — session identity); refused unless push is configured. "
        "Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal.py",
        "delete_push_subscription",
        "Driver portal. The Salis Driver is resolved from the session server-side "
        "(_resolve_driver); only the caller's own subscription (matched on "
        "driver + endpoint) is disabled, so one driver can never opt another's "
        "device out. Token/identity-resolved writer.",
    ),
    (
        "salis/doctype/rental_settlement/rental_settlement.py",
        "create_payment_request",
        "Doc-bound whitelisted method (def create_payment_request(self)). Frappe "
        "requires access to `self` to call it, the raised request is inserted "
        "WITH permissions (no ignore_permissions), and it is gated on "
        "self.docstatus==1 / status=='Approved'. Not a free-floating writer.",
    ),
    (
        "salis/api/boarding_flow.py",
        "get_trip_boarding",
        "Driver panel read. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (boarding._resolve_trip: own trip for a driver, "
        "any for Salis staff, raises PermissionError otherwise) before any access; "
        "the only write is a read-time system-timeout auto-confirm. "
        "Trip-scope-resolved.",
    ),
    (
        "salis/api/boarding_flow.py",
        "notify_remaining_passengers",
        "Driver action. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (own trip for a driver, any for Salis staff, "
        "raises PermissionError otherwise) before the write; only the trip's own "
        "Pending rows are nudged. Trip-scope-resolved writer.",
    ),
    (
        "salis/api/boarding_flow.py",
        "worker_request_wait",
        "Masar guest endpoint. allow_guest; the worker is resolved server-side from "
        "the Masar token (_resolve_worker, never client-supplied) and only their own "
        "row on their own today's trip is written; explicit rate_limit. A Guest has "
        "no role to permission-check.",
    ),
    (
        "salis/api/boarding_flow.py",
        "worker_claim_boarded",
        "Masar guest endpoint. allow_guest; the worker is resolved server-side from "
        "the Masar token (_resolve_worker) and only their own boarding-state row on "
        "their own today's trip is written; explicit rate_limit. A Guest has no role "
        "to permission-check.",
    ),
    (
        "salis/api/boarding_flow.py",
        "driver_confirm_boarding",
        "Driver action. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (own trip for a driver, any for Salis staff, "
        "raises PermissionError otherwise) before the confirm/reject write. "
        "Trip-scope-resolved writer.",
    ),
    (
        "salis/api/boarding_flow.py",
        "worker_trip_boarding",
        "Masar guest poll. allow_guest; the worker is resolved server-side from the "
        "Masar token (_resolve_worker) and returns only their own state; the lone "
        "write is a read-time system-timeout auto-confirm. A Guest has no role to "
        "permission-check.",
    ),
    (
        "salis/api/boarding_flow.py",
        "depart_and_finalize",
        "Driver action. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (own trip for a driver, any for Salis staff, "
        "raises PermissionError otherwise) before the finalize write. "
        "Trip-scope-resolved writer.",
    ),
]


def _python_files():
    pattern = os.path.join(APP_ROOT, "**", "*.py")
    return sorted(glob.glob(pattern, recursive=True))


def _has_write_call(func_node):
    """Return True if the function body contains any recognised write call."""
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            # [#oss4x5]
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in WRITE_CALLS:
                    return True
            elif isinstance(node.func, ast.Name):
                if node.func.id in WRITE_CALLS:
                    return True
    return False


def _decorator_has_methods_post(decorator):
    """Return True if the decorator node contains methods=["POST"]."""
    if not isinstance(decorator, ast.Call):
        return False
    for keyword in decorator.keywords:
        if keyword.arg == "methods":
            val = keyword.value
            if isinstance(val, ast.List):
                for elt in val.elts:
                    if isinstance(elt, ast.Constant) and elt.value == "POST":
                        return True
    return False


def _is_bare_whitelist(decorator):
    """Return True if the decorator is @frappe.whitelist() without methods=.

    Matches:
        @frappe.whitelist()
        @frappe.whitelist(allow_guest=True)   — also unsafe for writes

    Does NOT match:
        @frappe.whitelist(methods=["POST"])
    """
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    # [#s1tia9]
    is_whitelist = (
        (isinstance(func, ast.Attribute) and func.attr == "whitelist")
        or (isinstance(func, ast.Name) and func.id == "whitelist")
    )
    if not is_whitelist:
        return False
    return not _decorator_has_methods_post(decorator)


def _is_whitelisted(decorator):
    """True if the decorator is any @frappe.whitelist(...) / @whitelist(...)."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    return (
        (isinstance(func, ast.Attribute) and func.attr == "whitelist")
        or (isinstance(func, ast.Name) and func.id == "whitelist")
    )


def _called_local_funcs(func_node):
    """Names of bare-name function calls in the body, e.g. ``route_payment(x)``.

    Used to follow ONE level of intra-module delegation: a whitelisted endpoint
    that delegates its write to a module-level helper (``return route_payment(...)``)
    is still a write endpoint, and the permission check may legitimately live in
    either the endpoint or that helper.
    """
    out = set()
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            out.add(n.func.id)
    return out


def _has_permission_call(func_node):
    """True if the function body calls has_permission / check_permission."""
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in PERMISSION_CALLS:
                return True
            if isinstance(f, ast.Name) and f.id in PERMISSION_CALLS:
                return True
    return False


def _collect_permission_violations():
    """Scan all Python files for whitelisted POST write endpoints that do not
    recheck permission (directly or via a one-hop module-level delegate) and are
    not in PERMISSION_RECHECK_ALLOWLIST.

    Returns a list of (rel_path, func_name, lineno).
    """
    violations = []
    allow_keys = {(p, fn) for p, fn, _ in PERMISSION_RECHECK_ALLOWLIST}

    for fpath in _python_files():
        rel = os.path.relpath(fpath, APP_ROOT)
        with open(fpath, encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source, filename=fpath)
        except SyntaxError:
            continue

        # [#q7g9d0]
        local_funcs = {
            n.name: n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not any(_is_whitelisted(d) for d in node.decorator_list):
                continue

            # [#boq4cv]
            writes = _has_write_call(node)
            delegates = _called_local_funcs(node)
            if not writes:
                for callee in delegates:
                    target = local_funcs.get(callee)
                    if target is not None and _has_write_call(target):
                        writes = True
                        break
            if not writes:
                continue

            if (rel, node.name) in allow_keys:
                continue

            # [#a9el4t]
            checked = _has_permission_call(node)
            if not checked:
                for callee in delegates:
                    target = local_funcs.get(callee)
                    if target is not None and _has_permission_call(target):
                        checked = True
                        break
            if checked:
                continue

            violations.append((rel, node.name, node.lineno))

    return violations


def _collect_violations():
    """Scan all Python files; return list of (rel_path, func_name, lineno)."""
    violations = []
    safe_keys = {(p, fn) for p, fn, _ in SAFE_ALLOWLIST}

    for fpath in _python_files():
        rel = os.path.relpath(fpath, APP_ROOT)
        with open(fpath, encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source, filename=fpath)
        except SyntaxError:
            continue  # Syntax errors caught by other tests / ruff

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            # [#s9nulg]
            bare = [d for d in node.decorator_list if _is_bare_whitelist(d)]
            if not bare:
                continue
            # [#hz4b3c]
            if not _has_write_call(node):
                continue
            # [#9jo2d6]
            if (rel, node.name) in safe_keys:
                continue
            violations.append((rel, node.name, node.lineno))

    return violations


class TestHttpMethodEnforcement(unittest.TestCase):

    def test_no_write_endpoint_without_post_restriction(self):
        """All whitelisted write endpoints must declare methods=['POST'].

        If this test fails, the reported function performs database writes but
        its @frappe.whitelist() decorator does not restrict the HTTP method to
        POST. This means the write can be triggered via a GET request.

        Remediation options:
          1. Add methods=['POST'] to the decorator.
          2. If the function is actually read-only, add it to SAFE_ALLOWLIST
             in this test file with a comment explaining why it is safe.
        """
        violations = _collect_violations()
        if violations:
            details = "\n".join(
                f"  {rel}:{lineno}  def {fn}()" for rel, fn, lineno in violations
            )
            self.fail(
                f"Found {len(violations)} whitelisted write endpoint(s) without "
                f"methods=['POST']:\n{details}\n\n"
                "Add methods=['POST'] to the decorator, or add the function to "
                "SAFE_ALLOWLIST in test_http_enforcement.py with a justification."
            )

    def test_write_endpoints_recheck_permission(self):
        """Every non-allowlisted whitelisted write endpoint must recheck permission.

        A whitelisted endpoint that performs a write (directly, or via a one-hop
        module-level delegate such as ``create_routed_payment -> route_payment``)
        MUST call ``frappe.has_permission(...)`` / ``check_permission(...)`` so
        the Frappe permission system — including per-doc ``has_permission``
        hooks — gates the write. Being finance-approved / submitted is a property
        of the target document, NOT an authorisation of the caller.

        The only exemptions are the token-/identity-resolved guest writers in
        PERMISSION_RECHECK_ALLOWLIST, whose authorisation is a movement token or
        a server-side identity resolution rather than a desk permission.

        If this test fails, the reported endpoint writes without rechecking
        permission. Remediation:
          1. Add ``frappe.has_permission("<DocType>", "write", doc=<doc>,
             throw=True)`` (and a ``"submit"`` check if it submits) BEFORE any
             side effect.
          2. If it is a legitimately token/identity-resolved guest writer, add it
             to PERMISSION_RECHECK_ALLOWLIST with a justification.
        """
        violations = _collect_permission_violations()
        if violations:
            details = "\n".join(
                f"  {rel}:{lineno}  def {fn}()" for rel, fn, lineno in violations
            )
            self.fail(
                f"Found {len(violations)} whitelisted write endpoint(s) that do "
                f"not recheck permission:\n{details}\n\n"
                "Add frappe.has_permission(...) / check_permission(...) before "
                "the write, or add the endpoint to PERMISSION_RECHECK_ALLOWLIST "
                "in test_http_enforcement.py with a justification."
            )

    def test_permission_recheck_allowlist_entries_still_exist(self):
        """Every PERMISSION_RECHECK_ALLOWLIST entry must still resolve.

        Catches stale exemptions when a token/identity writer is renamed or
        removed (which would silently drop it from the guarded set).
        """
        for rel_path, func_name, _reason in PERMISSION_RECHECK_ALLOWLIST:
            abs_path = os.path.join(APP_ROOT, rel_path)
            with self.subTest(path=rel_path, func=func_name):
                self.assertTrue(
                    os.path.exists(abs_path),
                    f"PERMISSION_RECHECK_ALLOWLIST references '{rel_path}' which "
                    "does not exist.",
                )
                with open(abs_path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                func_names = {
                    n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                }
                self.assertIn(
                    func_name,
                    func_names,
                    f"PERMISSION_RECHECK_ALLOWLIST references '{func_name}' in "
                    f"'{rel_path}' but the function no longer exists.",
                )

    def test_allowlist_entries_still_exist(self):
        """Every entry in SAFE_ALLOWLIST must still exist in the source tree.

        This catches stale allowlist entries when functions are renamed or
        removed.
        """
        for rel_path, func_name, reason in SAFE_ALLOWLIST:
            abs_path = os.path.join(APP_ROOT, rel_path)
            with self.subTest(path=rel_path, func=func_name):
                self.assertTrue(
                    os.path.exists(abs_path),
                    f"SAFE_ALLOWLIST references '{rel_path}' which does not exist.",
                )
                with open(abs_path, encoding="utf-8") as fh:
                    source = fh.read()
                tree = ast.parse(source)
                func_names = {
                    n.name
                    for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                }
                self.assertIn(
                    func_name,
                    func_names,
                    f"SAFE_ALLOWLIST references function '{func_name}' in '{rel_path}' "
                    "but the function no longer exists.",
                )


if __name__ == "__main__":
    unittest.main()
