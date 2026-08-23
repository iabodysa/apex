# Copyright (c) 2026, afmcoltd

"""The scope fragment renderers Habitat and Salis both dispatch through.

These build the WHERE fragment that confines a list or report to the caller's own
estate, so the two properties that matter are the exact SQL emitted and the behaviour
on a key no table defines. An unknown strategy MUST render ``1=0`` and never an empty
string: an empty fragment is no restriction at all, which turns a scoping failure into
a silent grant of every row.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.permission_scope import (
    quote_column,
    render_column,
    render_dual,
    render_fragment,
)


class TestScopeFragments(FrappeTestCase):
    """Pure string construction — no records, no session, no permissions."""

    def test_quote_column_wraps_exactly_once(self):
        self.assertEqual(quote_column("building"), "`building`")

    def test_render_column_holds_the_row_column_to_the_values(self):
        self.assertEqual(
            render_column({"field": "building"}, "'B1', 'B2'"),
            "`building` in ('B1', 'B2')",
        )

    def test_render_dual_ors_the_two_endpoints_inside_one_fragment(self):
        """Frappe AND-joins separate conditions, so an either-endpoint scope has to
        arrive already OR-ed or a row crossing the boundary is hidden."""
        fragment = render_dual({"first": "from_building", "second": "to_building"}, "'B1'")
        self.assertEqual(
            fragment, "(`from_building` in ('B1') or `to_building` in ('B1'))"
        )
        self.assertTrue(fragment.startswith("(") and fragment.endswith(")"))

    def test_unknown_strategy_fails_closed(self):
        self.assertEqual(render_fragment("no-such-kind", {}, ["B1"], {}), "1=0")

    def test_render_fragment_escapes_every_value_it_is_given(self):
        fragments = {"column": render_column}
        rendered = render_fragment("column", {"field": "building"}, ["B'1", "B2"], fragments)
        self.assertEqual(rendered, "`building` in ('B\\'1', 'B2')")

    def test_each_module_keeps_its_own_strategy_table(self):
        """The dispatcher takes the table, so Habitat's keys never resolve Salis's."""
        from apex.habitat import permissions as habitat
        from apex.salis import permissions as salis

        self.assertIn("column", habitat.FRAGMENTS)
        self.assertIn("column", salis.FRAGMENTS)
        self.assertEqual(
            habitat.FRAGMENTS["column"]({"field": "building"}, "'B1'"),
            "`building` in ('B1')",
        )
        self.assertEqual(
            salis.FRAGMENTS["column"]({"field": "project"}, "'P1'"),
            "`project` in ('P1')",
        )
        self.assertNotIn("trip", habitat.FRAGMENTS)


class TestResolveUser(FrappeTestCase):
    """The one answer to "who is asking" that every scope resolver enters through."""

    def test_none_falls_back_to_the_session_user(self):
        from apex.apex_core.utils.permission_scope import resolve_user

        self.assertEqual(resolve_user(None), frappe.session.user)
        self.assertEqual(resolve_user(), frappe.session.user)

    def test_an_explicit_user_is_returned_unchanged(self):
        from apex.apex_core.utils.permission_scope import resolve_user

        self.assertEqual(resolve_user("someone@example.com"), "someone@example.com")
