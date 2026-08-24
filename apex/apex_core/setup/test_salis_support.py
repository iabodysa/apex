# Copyright (c) 2026, afmcoltd


import ast
import inspect

from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.salis_support import _parse_workdays


class TestParseWorkdaysParsesThroughTheOneFrappePrimitive(FrappeTestCase):
    def test_json_branch_calls_frappe_parse_json_not_json_loads(self):
        tree = ast.parse(inspect.getsource(_parse_workdays))
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
            "_parse_workdays no longer calls frappe.parse_json",
        )
        self.assertFalse(
            any(_is_attr_call(c, "json", "loads") for c in calls),
            "_parse_workdays hand-rolls json.loads instead of frappe.parse_json",
        )

    def test_a_json_array_string_still_parses(self):
        self.assertEqual(_parse_workdays('["Friday", "Saturday"]'), ["Friday", "Saturday"])

    def test_the_comma_fallback_still_works_for_non_json_text(self):
        self.assertEqual(_parse_workdays("Friday, Saturday"), ["Friday", "Saturday"])

    def test_blank_and_none_both_return_empty(self):
        self.assertEqual(_parse_workdays(""), [])
        self.assertEqual(_parse_workdays(None), [])
