# Copyright (c) 2026, afmcoltd


import ast
import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.masar_worker import _clean_adhoc_passengers


class TestCleanAdhocPassengersParsesThroughTheOneFrappePrimitive(FrappeTestCase):
    def test_no_hand_rolled_isinstance_guard_around_json_loads(self):
        tree = ast.parse(inspect.getsource(_clean_adhoc_passengers))
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
            "_clean_adhoc_passengers no longer calls frappe.parse_json",
        )
        self.assertFalse(
            any(_is_attr_call(c, "json", "loads") for c in calls),
            "_clean_adhoc_passengers hand-rolls json.loads instead of frappe.parse_json",
        )

    def test_a_json_string_of_rows_is_accepted(self):
        rows = _clean_adhoc_passengers(
            '[{"full_name": "Ali", "id_number": "100"}]'
        )
        self.assertEqual(rows[0]["full_name"], "Ali")
        self.assertEqual(rows[0]["id_number"], "100")

    def test_an_already_parsed_list_is_accepted_too(self):
        rows = _clean_adhoc_passengers([{"full_name": "Ali", "id_number": "100"}])
        self.assertEqual(rows[0]["full_name"], "Ali")

    def test_a_row_missing_an_id_number_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            _clean_adhoc_passengers([{"full_name": "Ali"}])
