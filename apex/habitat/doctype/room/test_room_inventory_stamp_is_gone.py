# Copyright (c) 2026, afmcoltd
"""A Room field nothing writes, named in a search index and printed on the wall label.

``last_inventory_date`` was read-only and its ONLY writer was
``building.update_room_inventory``, a whitelisted POST with no caller anywhere in the
app — the live readiness path is ``front_desk.set_room_readiness``, which the desk board
and the portal both call. So the field was blank on every Room, sat in the list view's
search index, and printed an empty line on the room label.

Graded here as a rule rather than an absence: every fieldname the list view searches on
must be a field the DocType actually has, and no Building endpoint may be a second
writer of Room readiness.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from apex.habitat.doctype.building import building


class TestRoomSearchFieldsResolve(TestCase):
    def _meta(self):
        return json.loads(
            (Path(__file__).with_name("room.json")).read_text(encoding="utf-8")
        )

    def test_every_search_field_is_a_field_of_room(self):
        meta = self._meta()
        fieldnames = {field["fieldname"] for field in meta["fields"]} | {"name"}
        searched = [part.strip() for part in meta["search_fields"].split(",")]

        self.assertTrue(searched, "the list view still searches on something")
        self.assertEqual(
            [name for name in searched if name not in fieldnames],
            [],
            "search_fields names a column the DocType does not have",
        )

    def test_no_write_only_inventory_stamp_survives(self):
        self.assertNotIn(
            "last_inventory_date",
            {field["fieldname"] for field in self._meta()["fields"]},
            "the field's only writer was deleted; a field nothing can write is not a record",
        )

    def test_building_publishes_no_second_room_readiness_writer(self):
        self.assertFalse(
            hasattr(building, "update_room_inventory"),
            "readiness is set through front_desk.set_room_readiness, which has callers",
        )
