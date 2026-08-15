# Copyright (c) 2026, afmcoltd
"""``bill_share_note`` is persisted prose, so it has to be translatable prose.

It is written to the row, shown on the form, and copied into the Accommodation Ledger's
remarks. Composed as an f-string it wrote English into the database of an Arabic site,
and no translator ever saw it. One whole-sentence msgid with positional placeholders is
what a translator can work with; four separately-translated fragments are not.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from apex.habitat.doctype.utility_bill_entry import utility_bill_entry


class TestBillShareNoteIsTranslated(TestCase):
    def _compute(self, pct):
        doc = SimpleNamespace(
            total_bill_amount=1000,
            cost_bearing_pct=pct,
            bill_amount=None,
            bill_share_note=None,
        )
        seen = []

        def gettext(message):
            seen.append(message)
            return message

        # fmt_money reads the site's currency format; the note's wording, not its number
        # formatting, is what is graded here.
        with (
            patch.object(utility_bill_entry, "_", side_effect=gettext),
            patch.object(
                utility_bill_entry, "fmt_money", side_effect=lambda amount, **_kw: f"SAR {amount}"
            ),
        ):
            utility_bill_entry._compute_sharing(doc)
        return doc, seen

    def test_the_shared_meter_note_is_one_translatable_sentence(self):
        doc, seen = self._compute(40.0)

        self.assertEqual(
            seen,
            ["Shared meter — {0}% of {1} = {2} (building share)"],
            "the note must reach the translator as one msgid with positional placeholders",
        )
        self.assertIn("40.0%", doc.bill_share_note)
        self.assertIn("(building share)", doc.bill_share_note)

    def test_a_full_bearing_bill_writes_no_note_and_asks_for_no_translation(self):
        doc, seen = self._compute(100.0)
        self.assertEqual(doc.bill_share_note, "")
        self.assertEqual(seen, [])
