# Copyright (c) 2026, afmcoltd


import frappe
from frappe.realtime import get_doc_room, get_doctype_room, get_site_room
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import portal_live


class TestPortalLiveRooms(FrappeTestCase):

    def setUp(self):
        self.published = []
        self._real_publish = frappe.publish_realtime
        frappe.publish_realtime = lambda *args, **kwargs: self.published.append((args, kwargs))
        self.addCleanup(self._restore)

    def _restore(self):
        frappe.publish_realtime = self._real_publish

    def _room(self):
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
        portal_live.notify_building("B-TEST")
        self.assertTrue(self.published[0][1].get("after_commit"))

    def test_blank_building_publishes_nothing(self):
        self.assertFalse(portal_live.notify_building(""))
        self.assertFalse(portal_live.notify_building(None))
        self.assertEqual(self.published, [])

    def test_doctype_doorbell_names_the_doctype_room(self):
        self.assertTrue(portal_live.notify_doctype("Salis Vehicle", "fleet_update", {"plate": "X"}))
        self.assertEqual(self._room(), get_doctype_room("Salis Vehicle"))
        self.assertNotEqual(self._room(), get_site_room())

    def test_doctype_doorbell_carries_only_what_the_caller_passed(self):
        portal_live.notify_doctype("Dispatch Trip", "driver_trip_update", {"name": "T-1"})
        (args, _kwargs) = self.published[0]
        self.assertEqual(args[1], {"name": "T-1"})

    def test_doctype_doorbell_defaults_to_an_empty_payload(self):
        portal_live.notify_doctype("Dispatch Trip", "driver_trip_update")
        self.assertEqual(self.published[0][0][1], {})
