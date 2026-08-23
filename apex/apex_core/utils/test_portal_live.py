# Copyright (c) 2026, afmcoltd

"""The room each portal doorbell rings.

The property under test is the ROOM, not the event: ``publish_realtime`` accepts a
``doctype`` with no ``docname`` and silently routes that event to the site room
``"all"``, which every System User joins with no permission check
(frappe/realtime/handlers/frappe_handlers.js:12). A doorbell meant for one building's
receptionists or one operations board would then be delivered to the whole desk, and
never to the portal it was written for. These tests read the room off the publish and
fail if it is ever the site room again.
"""

import frappe
from frappe.realtime import get_doc_room, get_doctype_room, get_site_room
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import portal_live


class TestPortalLiveRooms(FrappeTestCase):
    """Pure routing — no records, no session, no socket."""

    def setUp(self):
        self.published = []
        self._real_publish = frappe.publish_realtime
        frappe.publish_realtime = lambda *args, **kwargs: self.published.append((args, kwargs))
        self.addCleanup(self._restore)

    def _restore(self):
        frappe.publish_realtime = self._real_publish

    def _room(self):
        """The room the single captured publish would resolve to."""
        (_args, kwargs) = self.published[0]
        if kwargs.get("room"):
            return kwargs["room"]
        if kwargs.get("doctype") and kwargs.get("docname"):
            return get_doc_room(kwargs["doctype"], kwargs["docname"])
        return get_site_room()

    def test_building_doorbell_rings_the_building_doc_room(self):
        self.assertTrue(portal_live.notify_building("B-TEST"))
        self.assertEqual(len(self.published), 1)
        self.assertEqual(self._room(), get_doc_room("Building", "B-TEST"))
        self.assertNotEqual(self._room(), get_site_room())

    def test_building_doorbell_is_after_commit(self):
        """A watcher told about a row the transaction rolls back refetches nothing."""
        portal_live.notify_building("B-TEST")
        self.assertTrue(self.published[0][1].get("after_commit"))

    def test_blank_building_publishes_nothing(self):
        """The empty case is the dangerous one: with no docname the same call would
        broadcast a building's change to every System User on the site."""
        self.assertFalse(portal_live.notify_building(""))
        self.assertFalse(portal_live.notify_building(None))
        self.assertEqual(self.published, [])

    def test_doctype_doorbell_names_the_doctype_room(self):
        self.assertTrue(portal_live.notify_doctype("Salis Vehicle", "fleet_update", {"plate": "X"}))
        self.assertEqual(self._room(), get_doctype_room("Salis Vehicle"))
        self.assertNotEqual(self._room(), get_site_room())

    def test_doctype_doorbell_carries_only_what_the_caller_passed(self):
        """No session user, no rider and no resident is added on the way out."""
        portal_live.notify_doctype("Dispatch Trip", "driver_trip_update", {"name": "T-1"})
        (args, _kwargs) = self.published[0]
        self.assertEqual(args[1], {"name": "T-1"})

    def test_doctype_doorbell_defaults_to_an_empty_payload(self):
        portal_live.notify_doctype("Dispatch Trip", "driver_trip_update")
        self.assertEqual(self.published[0][0][1], {})
