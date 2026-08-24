# Copyright (c) 2026, afmcoltd
"""Tests for Building's abbreviation lock.

Patterned on frappe/tests/test_document.py. The building is built and saved
through ``apex.tests.factories.make_building``/``make_room`` and then
re-saved so ``before_save``'s ``_guard_abbreviation_lock`` in
``building.py`` -- wired through hooks.py's doc_events, not the class body
-- is what is exercised, not a stub.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building, make_room


class TestBuildingAbbreviationLock(FrappeTestCase):
    def test_changing_the_abbreviation_after_a_room_exists_is_refused(self):
        building = make_building("Test Building Abbrev Lock")
        building.abbreviation = "LOCK1"
        building.save(ignore_permissions=True)
        make_room(building.name, room_number=f"{building.name}-R99")

        building.reload()
        building.abbreviation = "LOCK2"
        with self.assertRaises(frappe.ValidationError):
            building.save(ignore_permissions=True)
