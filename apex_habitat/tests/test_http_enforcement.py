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
