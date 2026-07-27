# Copyright (c) 2026, AFMCO and contributors
"""The Salis Driver desk surface for the Driver Portal barcode.

Stdlib-only by design: it reads the two client scripts and the token controller as
text/AST, so it runs with no bench and no site. What it guards is the wiring a
runtime test cannot see cheaply — which server method each button actually calls,
whether that method exists and is whitelisted, and whether the surface that hands
out a bearer credential writes it anywhere a browser keeps.

Why the wiring is load-bearing rather than cosmetic: a driver signs in by scanning
a barcode, with no account and no password, so whoever holds the link IS that
driver to every driver-portal endpoint. Before this card the only shipped issuance
button lived on the token record and called the WORKER endpoint with
``frm.doc.employee`` — which on a Driver-holder row is undefined. A button aimed
at the wrong endpoint is an outage at best and a mis-scoped credential at worst.

The runtime half of the contract (who may issue, who may revoke, what the audit
trail records, what an old link can still do) lives beside the controller, in
apex/apex_core/doctype/masar_worker_token/test_masar_worker_token_desk_issuance.py.
"""

import ast
import re
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]
DRIVER_JS = Path(__file__).resolve().parent / "salis_driver.js"
TOKEN_DIR = APP_ROOT / "apex_core" / "doctype" / "masar_worker_token"
TOKEN_JS = TOKEN_DIR / "masar_worker_token.js"
TOKEN_PY = TOKEN_DIR / "masar_worker_token.py"
LINK_BUNDLE = APP_ROOT / "public" / "js" / "masar_worker_link.bundle.js"

TOKEN_MODULE = "apex.apex_core.doctype.masar_worker_token.masar_worker_token"
_ENDPOINT = re.compile(re.escape(TOKEN_MODULE) + r"\.([A-Za-z_][A-Za-z0-9_]*)")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _endpoints_called_from(path: Path) -> set[str]:
    """Names of token-module endpoints a client script routes a button to."""
    return set(_ENDPOINT.findall(_read(path)))


def _whitelisted_functions(path: Path) -> set[str]:
    """Module-level functions carrying any ``@frappe.whitelist(...)`` decorator."""
    tree = ast.parse(_read(path), filename=str(path))
    out = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            func = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "whitelist":
                out.add(node.name)
    return out


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(_read(path), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined at module level in {path.name}")


def _call_names_in_order(func_node: ast.FunctionDef) -> list[str]:
    """Called names in source order — ``frappe.has_permission`` keeps its dotted form."""
    names = []
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.append((node.lineno, node.col_offset, func.id))
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            names.append((node.lineno, node.col_offset, f"{func.value.id}.{func.attr}"))
        elif isinstance(func, ast.Attribute):
            names.append((node.lineno, node.col_offset, func.attr))
    return [name for _line, _col, name in sorted(names)]


class TestSalisDriverPortalActions(unittest.TestCase):
    def test_driver_form_calls_only_the_driver_endpoints(self):
        """The driver form issues and revokes through the DRIVER endpoints only.

        The worker endpoint resolves its subject from an Employee id. Calling it
        from this form would either fail outright or, if a driver ever carried an
        employee link, mint the wrong audience's credential."""
        called = _endpoints_called_from(DRIVER_JS)
        self.assertEqual(called, {"issue_driver_link", "revoke_driver_link"})
        self.assertNotIn("issue_worker_link", _read(DRIVER_JS))

    def test_every_endpoint_the_desk_calls_is_whitelisted(self):
        """A button pointing at a non-whitelisted (or renamed) function is a dead
        surface that reviews pass and users find. Cross-checks the literal method
        paths in both client scripts against the controller's own decorators."""
        whitelisted = _whitelisted_functions(TOKEN_PY)
        self.assertIn("revoke_driver_link", whitelisted)
        called = _endpoints_called_from(DRIVER_JS) | _endpoints_called_from(TOKEN_JS)
        self.assertTrue(called, "endpoint scan found nothing — the regex is blind")
        self.assertEqual(called - whitelisted, set())

    def test_revocation_is_authorized_before_anything_is_disabled(self):
        """``revoke_driver_link`` must authorize BEFORE it revokes.

        Write permission on the token doctype is held by housing and HR roles too,
        so the doctype check alone would let an Accommodation Manager kill any
        driver's link. ``authorize_revocation`` is what narrows that to the fleet
        issuer roles and the caller's own project scope; ordering matters because a
        check after the write is not a check."""
        order = _call_names_in_order(_function(TOKEN_PY, "revoke_driver_link"))
        self.assertIn("frappe.has_permission", order)
        self.assertIn("authorize_revocation", order)
        self.assertIn("revoke_driver_tokens", order)
        self.assertLess(
            order.index("authorize_revocation"),
            order.index("revoke_driver_tokens"),
            "authorization must precede the revocation write",
        )

    def test_issuance_surface_never_parks_the_credential_in_the_browser(self):
        """The raw token is returned exactly once, to be shown and forgotten.

        A console line, a web-storage key or a cookie would each turn that one
        moment into a copy that outlives the driver's clearance, readable by anyone
        who later opens that browser profile."""
        for path in (DRIVER_JS, TOKEN_JS, LINK_BUNDLE):
            source = _read(path)
            for sink in ("console.", "localStorage", "sessionStorage", "document.cookie"):
                self.assertNotIn(sink, source, f"{path.name} writes the payload to {sink}")

    def test_token_record_routes_a_driver_row_to_the_driver_endpoint(self):
        """The token record's own action must branch on holder type.

        This is the bug the card names: a Driver-holder row has no ``employee``, so
        the single worker-only call site sent an undefined subject to the worker
        endpoint."""
        source = _read(TOKEN_JS)
        self.assertIn('frm.doc.holder_type === "Driver"', source)
        self.assertIn("frm.doc.driver", source)
        self.assertEqual(
            _endpoints_called_from(TOKEN_JS),
            {"issue_driver_link", "issue_worker_link"},
        )

    def test_both_audiences_keep_a_dialog_and_the_driver_form_uses_the_driver_one(self):
        """One dialog implementation, two named entry points.

        The worker entry point stays because Housing's arrival flow calls it by
        name; the driver form must call the driver one, which carries the
        no-password warning and the expiry."""
        bundle = _read(LINK_BUNDLE)
        for factory in ("show_portal_link_dialog", "show_worker_link_dialog", "show_driver_link_dialog"):
            self.assertIn(f"apex.masar.{factory} = function", bundle)
        self.assertIn("apex.masar.show_driver_link_dialog(", _read(DRIVER_JS))
        self.assertNotIn("show_worker_link_dialog", _read(DRIVER_JS))


if __name__ == "__main__":
    unittest.main()
