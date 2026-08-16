# Copyright (c) 2026, AFMCO and contributors
"""Two screenshot-audit defects on the fleet portal, graded against their current source.

EMPTY STATE: the audit that found three shapes for one state — two bare sentences with no
icon and no action, beside an error state that had both — graded a shared, barrel-exported
`EmptyState.vue` the fleet portal imported twice. That component, its barrel export and its
two import sites do not exist anywhere under frontend/apex_portal/: the rebuilt portal
decomposes each feature's loading, error and empty states into a local switcher instead of
one shared component, so the existence, slot and import-count checks that graded the old
component have no successor and are not reproduced here. The bare-sentence concern that
component existed to close is independent of that architecture choice, and it is graded
here against the fleet portal's current switcher.

NUMERALS: one line carried two numeral systems — "الأحد، ٢ أغسطس" in Arabic-Indic beside
"0 رحلة" in Latin — because dates went through `ar-SA` while every count reaching the page
stayed a raw JS number. frontend/apex_portal/core/displayLabels.js:87,93 pins every
Intl.DateTimeFormat call to `ar-SA-u-ca-gregory-nu-latn`, so a formatted date and a raw
count both read in Latin digits.

AVATAR: apex/www/test_portal_shell_contract.py:101-120 forbids the string
`context.user_full_name` in every portal controller, fleet.py included, so a per-user
avatar initial sourced from that field has no path into this app; no avatar or initial
markup of any kind reaches frontend/apex_portal/. The class that graded that avatar is not
reproduced here.

Static on purpose: they read the source that produces the screen, so they run anywhere and
fail the moment a fix regresses.
"""

import pathlib
import unittest

import apex

REPO = pathlib.Path(apex.__file__).resolve().parents[1]
ASYNC_PANEL = (
    REPO
    / "frontend"
    / "apex_portal"
    / "features"
    / "fleet-self-service"
    / "components"
    / "AsyncPanel.vue"
)
DISPLAY_LABELS = REPO / "frontend" / "apex_portal" / "core" / "displayLabels.js"


class TestSharedEmptyState(unittest.TestCase):
    """The shared, barrel-exported `EmptyState.vue` (icon slot plus action slot) that the
    fleet portal imported twice does not exist anywhere under frontend/apex_portal/: no
    file by that name, no barrel index.js exporting it, no `<EmptyState` usage in any
    `.vue` file in the tree. The portal's empty states are decomposed per feature instead
    of routed through one shared component, so the component-existence, slot and
    import-count checks this class once ran have no successor to grade.

    The requirement that emptiness reads as a status, not a bare sentence, is unrelated to
    that component choice and still applies. It fails today: the fleet portal's shared
    state switcher renders an icon-free, action-free empty branch."""

    def test_no_bare_sentence_is_left_as_an_empty_state(self):
        """PRODUCT DEFECT, left red: frontend/apex_portal/features/fleet-self-service/
        components/AsyncPanel.vue renders `state === 'empty'` as a decorative dash, a
        heading and a paragraph — no icon, no action — for every screen that reaches it
        (CurrentVehiclePage.vue, FuelQuotaPage.vue, RepresentativeHomePage.vue, and every
        list built on SimpleListPage.vue)."""
        source = ASYNC_PANEL.read_text(encoding="utf-8")
        marker = "state === 'empty'"
        self.assertIn(marker, source, "no empty-state branch found to grade")
        branch = source[source.index(marker):]
        branch = branch[: branch.index("</section>")]
        self.assertIn('name="icon"', branch, "the empty state carries no icon affordance")
        self.assertIn('name="action"', branch, "the empty state carries no action affordance")


class TestOneNumeralSystem(unittest.TestCase):
    """The pinned-locale formatter that stops the Arabic-Indic/Latin-digit mix sits in
    frontend/apex_portal/core/displayLabels.js:87 and :93, not in a per-portal App.vue: one
    `dateFormatter` and one `timeFormatter`, each built once at module scope and reused by
    every portal that imports `dateTimeLabel`. Neither constructor carries a named
    AR_LOCALE constant — the pinned locale is the literal `ar-SA-u-ca-gregory-nu-latn`,
    inlined at each call, adding a Gregorian-calendar extension the fleet portal's
    `ar-SA-u-nu-latn` did not carry."""

    def test_the_arabic_locale_is_pinned_to_latin_digits(self):
        source = DISPLAY_LABELS.read_text(encoding="utf-8")
        self.assertIn("ar-SA-u-ca-gregory-nu-latn", source)

    def test_every_formatter_takes_the_pinned_locale(self):
        """Graded on the constructor lines only: every Intl.DateTimeFormat or
        Intl.NumberFormat call in this file must carry the pinned locale literal."""
        source = DISPLAY_LABELS.read_text(encoding="utf-8")
        constructors = [
            line.strip() for line in source.splitlines()
            if "Intl.NumberFormat(" in line or "Intl.DateTimeFormat(" in line
        ]
        self.assertTrue(constructors, "no Intl formatter found to grade")
        for line in constructors:
            self.assertIn("ar-SA-u-ca-gregory-nu-latn", line, line[:80])


if __name__ == "__main__":
    unittest.main()
