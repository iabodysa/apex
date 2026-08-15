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


"""The lease and licence bodies used to be built by concatenating separately-translated
fragments — ``_("The lease for") building _("has ended")`` — around their placeholders.
That hands the translator four words with no sentence to agree with and forces English
word order onto Arabic. Each is now ONE msgid carrying positional placeholders.

``str.format`` is available inside a Jinja notification body on purpose: Frappe removes
``format`` and ``format_map`` from the sandbox's blocked attributes
(frappe/utils/jinja.py:12), so the environment built here mirrors the one that renders
these notifications.
"""

_SENTENCE_END = (".", "!", "?", ":")

_WHOLE_SENTENCE_BODIES = {
    "habitat___building_lease_expired": (
        {"building": "BLDG-1", "lease_end_date": "2026-08-01"},
        "The lease for building BLDG-1 has ended (2026-08-01).",
    ),
    "habitat___building_lease_expiring": (
        {"building": "BLDG-1", "lease_end_date": "2026-09-01"},
        "The lease for building BLDG-1 ends on 2026-09-01. "
        "Please review renewal or termination.",
    ),
    "habitat___building_license_expired": (
        {"name": "BL-1", "building": "BLDG-1", "expiry_date": "2026-08-01"},
        "Building License BL-1 for building BLDG-1 has expired (2026-08-01).",
    ),
    "habitat___building_license_expiring_soon": (
        {
            "name": "BL-2",
            "building": "BLDG-1",
            "license_type": "Civil Defence Certificate",
            "license_number": "LIC-9",
            "expiry_date": "2026-09-01",
        },
        "Building License BL-2 (Civil Defence Certificate LIC-9) for building BLDG-1 "
        "expires on 2026-09-01. Please start renewal.",
    ),
}


def _render_capturing_msgids(template: str, doc: dict) -> tuple[str, list[str]]:
    """Render one notification body the way Frappe does, recording every msgid."""
    from types import SimpleNamespace

    from jinja2.sandbox import SandboxedEnvironment

    seen: list[str] = []

    def gettext(message):
        seen.append(message)
        return message

    env = SandboxedEnvironment()
    rendered = env.from_string(template).render(_=gettext, doc=SimpleNamespace(**doc))
    return rendered, seen


class TestNotificationBodiesTranslateWholeSentences(unittest.TestCase):
    def _body(self, notification: str) -> str:
        path = APP_ROOT / "habitat" / "notification" / notification / f"{notification}.json"
        return json.loads(path.read_text(encoding="utf-8"))["message"]

    def test_each_body_renders_and_hands_the_translator_whole_sentences(self):
        for notification, (doc, expected) in _WHOLE_SENTENCE_BODIES.items():
            with self.subTest(notification=notification):
                rendered, msgids = _render_capturing_msgids(self._body(notification), doc)
                self.assertEqual(" ".join(rendered.split()), expected)
                self.assertTrue(msgids, "the body must still route through _()")
                for msgid in msgids:
                    self.assertTrue(
                        msgid.rstrip().endswith(_SENTENCE_END),
                        f"{notification} hands the translator the fragment {msgid!r}",
                    )

    def test_the_check_can_actually_see_a_concatenated_body(self):
        """Positive control: the shape that was replaced still fails the rule."""
        rendered, msgids = _render_capturing_msgids(
            '{{ _("The lease for") }} {{ doc.building }} {{ _("has ended") }}.',
            {"building": "BLDG-1"},
        )
        self.assertEqual(rendered, "The lease for BLDG-1 has ended.")
        self.assertFalse(
            all(msgid.rstrip().endswith(_SENTENCE_END) for msgid in msgids)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
