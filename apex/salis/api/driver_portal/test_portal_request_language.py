# Copyright (c) 2026, afmcoltd
"""Regression: a /driver endpoint answers in the language the portal declares.

``apex/www/driver.py`` calls ``render_in_arabic()`` so the SHELL renders Arabic, but
each endpoint the SPA then calls is a separate request. A driver is Guest, so
``frappe.translate.get_language`` falls past the logged-in short-circuit to the
phone's ``Accept-Language`` header or System Settings
(``frappe/translate.py:35-60``, applied once per request at ``frappe/auth.py:47``),
and every ``frappe.throw(_(...))`` in these endpoints painted an English refusal
inside an Arabic RTL screen.

Two halves are asserted, because either alone is worthless:

* ``_require_enabled`` pins the language, and pins it BEFORE its own refusal — a
  disabled-portal message is user-facing too.
* EVERY whitelisted endpoint of the portal really does call ``_require_enabled``.
  That is what makes one seam enough instead of twelve call sites; an endpoint
  added without it fails here rather than shipping an English refusal.

Pure unit tests — the module's ``frappe`` handle is replaced and the endpoint scan
reads source with ``ast``, so no site and no request.
"""

from __future__ import annotations

import ast
import glob
import os
import unittest
from unittest import mock

from apex.salis.api import driver_portal


PACKAGE_ROOT = os.path.dirname(os.path.realpath(driver_portal.__file__))
# board_worker is a /driver endpoint that lives outside the package but funnels
# through the same preamble, so the scan has to reach it too.
EXTRA_ENDPOINT_MODULES = (
    os.path.join(os.path.dirname(PACKAGE_ROOT), "manual_boarding.py"),
)

PREAMBLE = "_require_enabled"

# An endpoint that is a thin wrapper runs the preamble one frame deeper, inside the
# function it delegates to. Each entry names that delegate, and
# ``test_every_named_delegate_really_runs_the_preamble`` re-checks it, so the
# exemption cannot rot into a hole.
DELEGATED = {
    ("trips.py", "my_worker_route_today"): (
        "apex/salis/api/masar.py",
        "get_my_worker_route_today",
    ),
}


def _is_whitelisted(node):
    """True when the function carries a ``frappe.whitelist`` decorator."""
    for decorator in node.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(call, ast.Attribute) and call.attr == "whitelist":
            return True
    return False


def _calls(node):
    """Every plain function name called anywhere inside ``node``."""
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }


def portal_endpoints():
    """``[(module, function, calls)]`` for every whitelisted /driver endpoint."""
    paths = [
        path
        for path in sorted(glob.glob(os.path.join(PACKAGE_ROOT, "*.py")))
        if not os.path.basename(path).startswith("test_")
    ]
    paths.extend(EXTRA_ENDPOINT_MODULES)

    found = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_whitelisted(
                node
            ):
                found.append((os.path.basename(path), node.name, _calls(node)))
    return found


class TestDriverPortalRequestLanguage(unittest.TestCase):
    def test_the_preamble_pins_the_request_language(self):
        with mock.patch.object(driver_portal, "render_in_arabic") as pin, mock.patch.object(
            driver_portal, "_portal_enabled", return_value=True
        ):
            driver_portal._require_enabled()
        pin.assert_called_once_with()

    def test_the_disabled_refusal_is_itself_pinned(self):
        """The language is set before the throw, so the refusal resolves Arabic too."""
        order = []
        mock_frappe = mock.MagicMock()
        mock_frappe.throw.side_effect = lambda *a, **k: order.append("throw")

        with mock.patch.object(
            driver_portal, "render_in_arabic", side_effect=lambda: order.append("pin")
        ), mock.patch.object(
            driver_portal, "_portal_enabled", return_value=False
        ), mock.patch.object(
            driver_portal, "frappe", mock_frappe
        ), mock.patch.object(
            # The real translator needs a cache; the ORDER of the two calls is what
            # is under test, not the wording of the refusal.
            driver_portal,
            "_",
            lambda message: message,
        ):
            driver_portal._require_enabled()

        self.assertEqual(["pin", "throw"], order)

    def test_every_portal_endpoint_runs_the_preamble(self):
        endpoints = portal_endpoints()
        missing = [
            f"{module}:{name}"
            for module, name, calls in endpoints
            if PREAMBLE not in calls and (module, name) not in DELEGATED
        ]
        self.assertEqual(
            [],
            missing,
            f"these /driver endpoints skip {PREAMBLE}(), so their refusals resolve "
            f"in whatever language the phone asked for: {missing}",
        )

    def test_every_named_delegate_really_runs_the_preamble(self):
        """An exemption is only sound while the delegate it names still holds the line."""
        app_root = os.path.dirname(os.path.dirname(os.path.dirname(PACKAGE_ROOT)))
        for (module, name), (delegate_path, delegate_name) in DELEGATED.items():
            with self.subTest(endpoint=f"{module}:{name}"):
                path = os.path.join(os.path.dirname(app_root), delegate_path)
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
                bodies = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == delegate_name
                ]
                self.assertTrue(bodies, f"{delegate_path}:{delegate_name} is gone")
                self.assertIn(
                    PREAMBLE,
                    _calls(bodies[0]),
                    f"{module}:{name} is exempt because {delegate_name} runs "
                    f"{PREAMBLE}() for it — and it no longer does",
                )

    def test_the_endpoint_scan_is_not_silently_empty(self):
        """Guard of the guard: an empty scan passes the assertion above vacuously."""
        endpoints = portal_endpoints()
        self.assertGreaterEqual(
            len(endpoints), 10, f"endpoint scan found too few in {PACKAGE_ROOT}"
        )
        self.assertIn(
            "board_worker",
            {name for _module, name, _calls in endpoints},
            "the scan must reach manual_boarding, which shares this preamble",
        )


if __name__ == "__main__":
    unittest.main()
