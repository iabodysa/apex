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

# Write-operation AST call names that flag a function as performing writes.
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

# Allowlist: bare @frappe.whitelist() functions that are safe without
# methods=["POST"] because they only return data (read-only mapping helpers).
# Each entry is (module_relative_path, function_name, reason).
# make_work_order was previously allowlisted here as a read-only get_mapped_doc
# mapper. It is now declared methods=["POST"] explicitly (frappe.model.open_mapped_doc
# issues a POST), so it no longer needs an exemption and was removed from this list.
SAFE_ALLOWLIST = []


# --- Permission-recheck guard (T-099) -------------------------------------
#
# AST call names that count as an explicit server-side permission check. A
# write endpoint must either call one of these (so Frappe's permission system —
# including per-doc has_permission hooks — gates the write) or be an
# identity/token-resolved guest writer in PERMISSION_RECHECK_ALLOWLIST below.
PERMISSION_CALLS = {"has_permission", "check_permission"}

# Token-/identity-resolved write endpoints that are EXEMPT from the
# has_permission requirement because their authorisation comes from a movement
# token or a server-side identity resolution, NOT from the Frappe permission
# system (a Guest, or a portal caller, has no desk role to has_permission-check
# against). Each entry is (module_relative_path, function_name, reason).
#
# These were enumerated by auditing every POST write endpoint; only the
# genuinely token/identity-resolved guest writers are listed. Anything else that
# writes MUST call has_permission / check_permission.
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
        "salis/doctype/rental_settlement/rental_settlement.py",
        "create_payment_request",
        "Doc-bound whitelisted method (def create_payment_request(self)). Frappe "
        "requires access to `self` to call it, the raised request is inserted "
        "WITH permissions (no ignore_permissions), and it is gated on "
        "self.docstatus==1 / status=='Approved'. Not a free-floating writer.",
    ),
]


def _python_files():
    pattern = os.path.join(APP_ROOT, "**", "*.py")
    return sorted(glob.glob(pattern, recursive=True))


def _has_write_call(func_node):
    """Return True if the function body contains any recognised write call."""
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            # frappe.db.insert(...), doc.save(), doc.insert(), etc.
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
    # Accept frappe.whitelist or just whitelist
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

        # Index module-level functions so delegation can be followed within the
        # same file.
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

            # Is this endpoint a writer — directly, or via a one-hop local
            # delegate (e.g. create_routed_payment -> route_payment)?
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

            # Permission check may sit in the endpoint OR in a one-hop local
            # delegate it calls.
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
            # Check if any decorator is a bare @frappe.whitelist()
            bare = [d for d in node.decorator_list if _is_bare_whitelist(d)]
            if not bare:
                continue
            # The function has a bare whitelist — does it write?
            if not _has_write_call(node):
                continue
            # Write found — check allowlist
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
