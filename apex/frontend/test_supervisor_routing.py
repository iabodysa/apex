# Copyright (c) 2026, AFMCO and contributors
"""The supervisor screen has addresses: a plan lives in the URL, and the browser's own
history carries the back button and the reload.

frontend/apex_portal/features/transport-supervisor/routes.js defines one path per record
kind — `/assignments`, `/assignments/:name`, `/requests`, `/requests/:name`, `/trips`,
`/trips/:name`, `/map`, `/history` — routed through vue-router rather than through a
hand-rolled hash parser. `supervisorRedirects` in that file sends the address shape this
file once graded, `/plan/:name/:tab?`, to `/assignments`, so an old link still lands
somewhere live.

A supervisor record renders every populated section on one page instead of switching
between tabs (frontend/apex_portal/features/transport-supervisor/SupervisorPage.vue and
components/SupervisorRecordCollections.vue), so a record has no second URL segment left to
address: "the plan and the section" collapses to "the plan." A list route and its detail
route are two distinct paths rather than one screen toggling a selection, so arriving at
the list route can no longer race a default selection into overriding a deep link — there
is no default selection left to race. Neither concern is graded here.

What is still graded is what carries a plan address across a page load: the route
parameter is read back into the record shown, a plan card writes that address when
clicked, and the browser history mechanism vue-router is configured with is the one whose
back button and reload actually work.
"""

import pathlib
import unittest

import apex

REPO = pathlib.Path(apex.__file__).resolve().parents[1]
SUPERVISOR_FEATURE = REPO / "frontend" / "apex_portal" / "features" / "transport-supervisor"
ROUTER = REPO / "frontend" / "apex_portal" / "core" / "router.js"
SUPERVISOR_PAGE = SUPERVISOR_FEATURE / "SupervisorPage.vue"
ASSIGNMENTS_PAGE = SUPERVISOR_FEATURE / "pages" / "RouteAssignmentsPage.vue"


class TestSupervisorRouting(unittest.TestCase):
    def test_an_address_is_read_back_on_arrival(self):
        """SupervisorPage.vue reads the route parameter straight into the record it
        loads, rather than into a component-local selection a separate function has to
        reconcile with the address bar."""
        source = SUPERVISOR_PAGE.read_text(encoding="utf-8")
        self.assertIn('import { useRoute } from "vue-router"', source)
        self.assertIn("route.params.name", source)

    def test_a_selection_writes_its_address(self):
        """Clicking a plan is a RouterLink to that plan's own path, so the browser's
        address bar, history and reload all follow it without any code in this file."""
        source = ASSIGNMENTS_PAGE.read_text(encoding="utf-8")
        self.assertIn("<RouterLink", source)
        self.assertIn(':to="`/assignments/${encodeURIComponent(assignment.name)}`"', source)

    def test_the_back_button_is_listened_for(self):
        """createWebHashHistory is vue-router's own back-button and reload wiring; the
        portal router is built on it rather than on manual hashchange/popstate
        listeners."""
        source = ROUTER.read_text(encoding="utf-8")
        self.assertIn(
            "createRouter, createRouterMatcher, createWebHashHistory",
            source,
        )
        self.assertIn("history: history ?? createWebHashHistory()", source)


if __name__ == "__main__":
    unittest.main()
