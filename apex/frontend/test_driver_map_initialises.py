# Copyright (c) 2026, AFMCO and contributors
"""The live map is built when its canvas exists, not when a GPS fix arrives.

frontend/apex_portal/features/transport-supervisor/leafletAdapter.js carries the map's
build path for the supervisor board: `createLeafletAdapter().draw(root, positions)` is
called once trips are loaded, and creates the Leaflet map — `if (!map) { map = L.map(...)
`— unconditionally on `root` existing, never on any position being present. A driver's own
marker is a separate decision made per item, after the map already exists: `if
(item.has_position && driver)` gates the one `L.circleMarker(driver, ...)` call that draws
it, so a trip whose driver has not yet shared a location still gets a map, just no marker
for that driver.

frontend/apex_portal/features/transport-supervisor/TransportMapPage.vue reaches this
adapter from a routed page (`onMounted(load)`), not from a tab a parent view can leave
unmounted: vue-router only mounts the page when its own route is visited, so there is no
"tab becomes active later" moment left for a lazy build to miss. The activation guard this
file once graded is not reproduced here.

Static because the browser cannot be driven from a Python test process in this
environment: it grades the call sites that decide WHEN the map and its markers are built.
"""

import pathlib
import unittest

import apex

LEAFLET_ADAPTER = (
    pathlib.Path(apex.__file__).resolve().parents[1]
    / "frontend"
    / "apex_portal"
    / "features"
    / "transport-supervisor"
    / "leafletAdapter.js"
)


class TestMapIsBuiltWithoutAFix(unittest.TestCase):
    def setUp(self):
        self.source = LEAFLET_ADAPTER.read_text(encoding="utf-8")

    def test_the_load_path_builds_the_map_on_leaflet_alone(self):
        """`if (!map) {` guards the map's own creation — nothing about `has_position`
        appears before it, so a trip with no fix yet still gets a map."""
        self.assertIn("if (!map) {", self.source)
        gate = self.source[: self.source.index("if (!map) {")]
        self.assertNotIn("has_position", gate)

    def test_the_marker_still_waits_for_a_real_position(self):
        self.assertIn("if (item.has_position && driver) {", self.source)

    def test_nothing_is_ever_drawn_at_zero_zero(self):
        """Every driver-marker call in this file sits on the line right after the
        has_position guard that reaches it."""
        lines = self.source.splitlines()
        calls = [index for index, line in enumerate(lines) if "L.circleMarker(driver" in line]
        self.assertTrue(calls, "no driver marker call found to grade")
        for index in calls:
            self.assertIn("has_position", lines[index - 1], lines[index - 1].strip()[:80])


if __name__ == "__main__":
    unittest.main()
