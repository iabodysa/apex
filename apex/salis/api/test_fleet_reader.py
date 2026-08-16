# Copyright (c) 2026, AFMCO and contributors
"""Tests for the shared fleet-reader service both fleet surfaces (fleet-os,
operations-control) resolve scope and driver names through.

``scope_filter`` has three real outcomes -- unscoped, scoped-with-projects,
scoped-with-NO-projects -- and the third is the access-gap signal callers must
short-circuit on rather than falling through to an unfiltered query; a test that
only proved the first two would leave the actual gap untested. ``driver_names``
is a bounded dedup + lookup: it must not repeat an ``frappe.get_all`` per row and
must return an empty dict rather than querying at all when nothing has a driver.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_reader import driver_names, scope_filter


class TestFleetReaderScopeFilter(FrappeTestCase):
    def test_unscoped_user_gets_no_project_filter(self):
        with patch(
            "apex.salis.api.fleet_reader._permitted_projects",
            return_value=(True, None),
        ):
            unscoped, projects, filters = scope_filter()
        self.assertTrue(unscoped)
        self.assertIsNone(projects)
        self.assertEqual(filters, {})

    def test_scoped_user_with_projects_gets_an_in_filter(self):
        with patch(
            "apex.salis.api.fleet_reader._permitted_projects",
            return_value=(False, ["PRJ-1", "PRJ-2"]),
        ):
            unscoped, projects, filters = scope_filter()
        self.assertFalse(unscoped)
        self.assertEqual(projects, ["PRJ-1", "PRJ-2"])
        self.assertEqual(filters, {"project": ["in", ["PRJ-1", "PRJ-2"]]})

    def test_scoped_user_with_no_project_gets_a_none_filter_not_an_empty_one(self):
        """None is the access-gap signal: the caller must short-circuit to an
        empty result rather than fall through to an unfiltered (site-wide) query."""
        with patch(
            "apex.salis.api.fleet_reader._permitted_projects",
            return_value=(False, []),
        ):
            unscoped, projects, filters = scope_filter()
        self.assertFalse(unscoped)
        self.assertEqual(projects, [])
        self.assertIsNone(filters)


class TestFleetReaderDriverNames(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=8).upper()
        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"Fleet Reader Test Driver {tag}",
            }
        ).insert(ignore_permissions=True)

    def test_no_vehicle_has_a_driver_returns_empty_dict_without_querying(self):
        self.assertEqual(driver_names([{"current_driver": None}, {}]), {})

    def test_maps_current_driver_to_full_name_deduplicated(self):
        rows = [
            {"current_driver": self.driver.name},
            {"current_driver": self.driver.name},
            {"current_driver": None},
        ]
        result = driver_names(rows)
        self.assertEqual(result, {self.driver.name: self.driver.full_name})
