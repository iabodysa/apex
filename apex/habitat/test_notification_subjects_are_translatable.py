# Copyright (c) 2026, AFMCO and contributors
"""A notification's subject line is the half the recipient reads first.

Every shipped Habitat and Logistay Notification already routes its message body through
``_()``, and every one of them shipped its SUBJECT as raw English. On an Arabic site that
produces an English subject line and an English bell title over an Arabic body — on the
alerts an operator sees most: an expired building licence, an overdue custody return, a
suspended SIM.

Frappe renders both fields through the same Jinja environment, so ``{{ _("...") }}`` is
available in a subject exactly as it is in a message. The rule graded here is only that
the literal PROSE is wrapped; interpolation stays outside it, and codes that are not words
(the SAR currency code) stay as they are.

Salis is left out on purpose: its notifications belong to another writer.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
MODULES = ("habitat", "logistay")

# A run of literal text between Jinja blocks. Prose is a run holding a letter that is not
# already inside a _() call; punctuation, digits and separators are not prose.
_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
_NOT_PROSE = {"SAR"}


def _bare_prose(subject: str) -> list[str]:
    """The literal runs of a subject that carry words and are not translated."""
    bare = []
    for run in _JINJA.split(subject):
        for word in re.findall(r"[A-Za-z][A-Za-z'\-]*", run):
            if word not in _NOT_PROSE:
                bare.append(word)
    return bare


def _notifications():
    for module in MODULES:
        for path in sorted((APP_ROOT / module / "notification").glob("*/*.json")):
            yield path, json.loads(path.read_text(encoding="utf-8"))


class TestNotificationSubjectsAreTranslatable(unittest.TestCase):
    def test_every_subject_routes_its_prose_through_gettext(self):
        offenders = {
            doc["name"]: _bare_prose(doc.get("subject") or "")
            for _path, doc in _notifications()
            if _bare_prose(doc.get("subject") or "")
        }
        self.assertEqual(
            offenders, {},
            "these Notification subjects render in English on an Arabic site: "
            f"{offenders}",
        )

    def test_the_check_can_actually_see_an_untranslated_subject(self):
        """Positive control: the matcher is not vacuously green."""
        self.assertEqual(_bare_prose('Building License EXPIRED: {{ doc.name }}'),
                         ["Building", "License", "EXPIRED"])
        self.assertEqual(_bare_prose('{{ _("Building License EXPIRED") }}: {{ doc.name }}'), [])

    def test_there_are_notifications_to_grade(self):
        """The population is named, so a glob that stops matching cannot pass silently."""
        self.assertEqual(len(list(_notifications())), 23)


if __name__ == "__main__":
    unittest.main(verbosity=2)
