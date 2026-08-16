# Copyright (c) 2026, Apex contributors

"""Tests for the fleet operations portal page (``/fleet-os``).

``has_apps_screen_access`` gates the ``/apps`` app-selector tile that links onto this
page. It must refuse in every case ``get_context`` would refuse, or the tile advertises
a screen the click lands on denied.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user
from apex.www import fleet_os


class TestFleetOsAppsScreenAccess(FrappeTestCase):
    """``has_apps_screen_access`` gates the /apps app-selector tile's ``has_permission``."""

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_a_fleet_role_holder_sees_the_tile(self):
        """Every role in FLEET_ROLES holds read on Salis Vehicle by fixture, so it must pass."""
        for role in fleet_os.FLEET_ROLES:
            with self.subTest(role=role):
                holder = _user(f"a546-fleet-os-tile-{role.split()[0].lower()}@test.local", role)
                with as_user(holder):
                    self.assertTrue(fleet_os.has_apps_screen_access())

    def test_a_role_outside_the_set_does_not_see_the_tile(self):
        """A real shipped role that holds none of FLEET_ROLES must be refused."""
        outsider = _user("a546-fleet-os-tile-refused@test.local", "Internal Auditor")
        with as_user(outsider):
            self.assertFalse(fleet_os.has_apps_screen_access())

    def test_a_fleet_role_holder_refused_vehicle_read_does_not_see_the_tile(self):
        """FLEET_ROLES membership alone must not grant the tile.

        get_context() also requires frappe.has_permission("Salis Vehicle", "read"); a role
        holder that check refuses must not see a tile that opens onto the denied screen.
        """
        holder = _user("a546-fleet-os-tile-no-vehicle-read@test.local", "Fleet Supervisor")
        with as_user(holder), patch.object(frappe, "has_permission", return_value=False):
            self.assertFalse(fleet_os.has_apps_screen_access())
