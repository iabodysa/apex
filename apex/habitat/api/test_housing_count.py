# Copyright (c) 2026, afmcoltd

"""``submit_counts`` takes its JSON-or-list ``lines`` argument straight to
``frappe.parse_json`` (frappe/utils/__init__.py:875), which already runs the
``isinstance(x, str)`` check before calling ``json.loads``. This fails the
moment the function goes back to a hand-rolled ``isinstance`` guard ahead of
a bare ``json.loads``.
"""

import ast
import inspect

from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.housing_count import submit_counts


class TestSubmitCountsParsesThroughTheOneFrappePrimitive(FrappeTestCase):
    def test_submit_counts_parses_lines_through_frappe_parse_json(self):
        tree = ast.parse(inspect.getsource(submit_counts))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

        def _is_attr_call(node, owner, attr):
            return (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == attr
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == owner
            )

        self.assertTrue(
            any(_is_attr_call(c, "frappe", "parse_json") for c in calls),
            "submit_counts no longer calls frappe.parse_json",
        )
        self.assertFalse(
            any(_is_attr_call(c, "json", "loads") for c in calls),
            "submit_counts hand-rolls json.loads instead of frappe.parse_json",
        )
