# Copyright (c) 2026, AFMCO and contributors
"""Guard: the /fleet employee page's section nav must actually navigate.

The page shipped once with three inert anchors and `is-active` written straight
into the markup of the first one, so the highlight lied about where the reader
was and nothing in the suite noticed. The nav is pure front-end, so the only
gate that can catch a regression to that state is a source guard.

What is asserted, and why each one is the falsifiable part of "the nav works":

  * no static `class="is-active"` in the nav slot, and the class is bound to
    reactive state instead -- a hardcoded highlight is exactly the old bug;
  * every id the nav points at exists as a section in the template -- an anchor
    to a missing id scrolls nowhere;
  * the movement is wired: `scroll-behavior: smooth` plus a
    `scroll-margin-block-start` on the cards (so the sticky header does not
    cover the section the reader was sent to), and an IntersectionObserver whose
    callback actually writes the highlight state -- the word appearing in the
    file is equally true of an observer that never fires;
  * the highlight's TRACKING has a gate that can fail. No source guard can watch
    a scroll, so that half is proven by mounting the page (vitest, jsdom) and
    driving the observer; this suite only makes sure that proof still exists.
  * the nav survives narrow viewports: the shared shell hides its top nav below
    the tablet breakpoint, and this page has no second navigation to fall back
    on, so index.css must put it back -- RTL-safely, with logical properties.
"""

import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

# [#uv2nqr] Portal sources live beside the package, not inside it.
REPO_ROOT = os.path.dirname(frappe.get_app_path("apex"))
APP_VUE = f"{REPO_ROOT}/frontend/fleet/src/App.vue"
PAGE_CSS = f"{REPO_ROOT}/frontend/fleet/src/index.css"
# Runtime half of the proof. CI runs it as Portal Tests / shared-components
# (`npm test -w frontend_shared`); the shared harness is where it lives because
# fleet ships a bundle, not a test runner.
NAV_RUNTIME_TEST = (
    f"{REPO_ROOT}/frontend/frontend_shared/components/__tests__/fleet-employee-nav.test.mjs"
)

# The shared FleetPageShell hides .fleet-nav below --bp-tablet (768px).
TABLET_BREAKPOINT = 768

# `class="x"` but not `:class="x"` / `v-bind:class="x"`.
STATIC_CLASS = re.compile(r'(?<![:\w-])class\s*=\s*"([^"]*)"')


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _block(text, start_index):
    """Body of the {...}, [...] or (...) group whose opening bracket is at start_index."""
    opening = text[start_index]
    closing = {"{": "}", "[": "]", "(": ")"}[opening]
    depth = 0
    for i in range(start_index, len(text)):
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return text[start_index + 1 : i]
    raise AssertionError(f"unbalanced {opening} at offset {start_index}")


def _nav_slot(sfc):
    m = re.search(r"<template\s+#nav\s*>", sfc)
    assert m, "the fleet page no longer passes a #nav slot to the shell"
    end = sfc.index("</template>", m.end())
    return sfc[m.end() : end]


def _nav_ids(sfc):
    """Section ids the nav offers, read from the nav model in <script setup>."""
    m = re.search(r"\bnavItems\s*=\s*\[", sfc)
    assert m, "no navItems model found -- the nav is not data-driven"
    return re.findall(r'\bid:\s*"([^"]+)"', _block(sfc, m.end() - 1))


def _narrow_media_blocks(css):
    """Bodies of every `@media (max-width: N)` block with N below the tablet
    breakpoint -- where the shell has switched its top nav off."""
    out = []
    for m in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", css):
        if int(m.group(1)) < TABLET_BREAKPOINT:
            out.append(_block(css, m.end() - 1))
    return out


class TestFleetEmployeeNav(FrappeTestCase):
    def setUp(self):
        self.sfc = _read(APP_VUE)
        self.css = _read(PAGE_CSS)
        self.nav = _nav_slot(self.sfc)

    def test_active_state_is_bound_not_hardcoded(self):
        baked_in = [c for c in STATIC_CLASS.findall(self.nav) if "is-active" in c.split()]
        self.assertEqual(
            baked_in,
            [],
            "the nav highlight is written into the markup, so it cannot follow the "
            f"reader: static class(es) {baked_in}",
        )
        self.assertRegex(
            self.nav,
            r':class\s*=\s*"[^"]*\bis-active\b',
            "the nav highlight must be bound to reactive state",
        )
        self.assertRegex(
            self.nav,
            r':href\s*=\s*"[^"]*#|href\s*=\s*"#',
            "each nav item must stay a real in-page anchor",
        )

    def test_every_nav_item_targets_a_real_section(self):
        ids = _nav_ids(self.sfc)
        self.assertGreaterEqual(len(ids), 3, f"expected the three page sections, got {ids}")
        rendered = set(re.findall(r'\bid\s*=\s*"([^"]+)"', self.sfc))
        missing = [i for i in ids if i not in rendered]
        self.assertEqual(missing, [], f"nav item(s) pointing at no section: {missing}")

    def test_scrolling_and_the_spy_that_follows_it_are_wired(self):
        self.assertRegex(
            self.css,
            r"scroll-behavior:\s*smooth",
            "without smooth scrolling the nav gives no sense of movement",
        )
        self.assertRegex(
            self.css,
            r"\.emp-card[^{}]*\{[^{}]*scroll-margin-block-start",
            "the scrolled-to card needs header clearance or it lands under the sticky bar",
        )
        m = re.search(r"new\s+IntersectionObserver\s*\(", self.sfc)
        self.assertTrue(
            m,
            "nothing observes the scroll position, so the highlight cannot follow it",
        )
        # The observer has to WRITE the highlight, not merely exist: an observer
        # whose callback drops the entries leaves the class pinned to whatever the
        # page loaded with, which is the old hardcoded bug wearing a spy.
        self.assertRegex(
            _block(self.sfc, m.end() - 1),
            r"\bactiveSection\.value\s*=",
            "the scroll observer never assigns the active section",
        )

    def test_the_tracking_has_a_runtime_gate_that_can_fail(self):
        """No source guard can watch a scroll; this asserts the gate that can.

        Everything above is text. Whether reaching a section MARKS its nav item and
        UNMARKS the others is only answerable by mounting the page, which the vitest
        file below does: it stubs IntersectionObserver (jsdom has none, and the page
        skips the spy entirely when the constructor is missing), then feeds it the
        reader's position. Deleting that file would leave the tracking claim with no
        gate at all while this suite stayed green -- the exact shape of the
        partially-closed cards this test family exists to prevent.
        """
        self.assertTrue(
            os.path.exists(NAV_RUNTIME_TEST),
            f"the runtime proof of the nav highlight is gone: {NAV_RUNTIME_TEST}",
        )
        proof = _read(NAV_RUNTIME_TEST)
        self.assertIn(
            "fleet/src/App.vue",
            proof,
            "the runtime proof must mount the real page, not a stand-in",
        )
        self.assertIn(
            "IntersectionObserver",
            proof,
            "the runtime proof must drive the scroll spy, or it tests nothing new",
        )

    def test_nav_stays_reachable_and_rtl_safe_when_narrow(self):
        """The nav must survive a narrow viewport — by the shell or by this page.

        The shared shell used to hide it there, so this page carried a rule to put it
        back. The shell now wraps it into a scrolling row instead, which is why the
        override is gone: what matters is that nothing hides the nav, not which file
        keeps it visible.
        """
        restored = "\n".join(b for b in _narrow_media_blocks(self.css) if ".fleet-nav" in b)
        hidden = []
        for selector, body in re.findall(r"([^{}]*\.fleet-nav[^{}]*)\{([^{}]*)\}", restored):
            value = re.search(r"\bdisplay\s*:\s*([\w-]+)", body)
            if value and value.group(1) == "none":
                hidden.append(selector.strip())
        self.assertEqual(
            hidden,
            [],
            "a narrow-viewport rule hides the nav and this page offers no other "
            f"navigation: {hidden}",
        )
        physical = re.findall(r"\b(?:margin|padding|inset)?-?(?:left|right)\s*:", restored)
        self.assertEqual(
            physical,
            [],
            f"physical edges break the Arabic mirror -- use logical properties: {physical}",
        )
