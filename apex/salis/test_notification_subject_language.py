# Copyright (c) 2026, afmcoltd
"""Regression: a Salis Notification's subject must be translatable, like its body.

Every shipped Salis Notification wrapped its ``message`` in ``{{ _("...") }}`` and
left its ``subject`` a raw English literal, so an Arabic recipient got an English
subject line over an Arabic body. ``Notification.send`` renders both halves through
``frappe.render_template`` (``frappe/email/doctype/notification/notification.py:241,271``)
and the jinja environment binds ``_`` to ``frappe._``
(``frappe/utils/safe_exec.py:275``), so the subject can carry the same wrapper the
message already does.

The assertion is mechanical rather than a list of ten expected strings: strip every
``{{ ... }}`` expression out of the subject and what is left must carry no letters.
A new notification shipped with a bare English subject fails without anyone
remembering to add it here.

Pure unit test — it reads the shipped JSON off disk, so it needs no site.
"""

from __future__ import annotations

import glob
import json
import os
import re
import unittest
from pathlib import Path

import apex


SALIS_ROOT = os.path.join(str(Path(apex.__file__).resolve().parent), "salis")
NOTIFICATION_GLOB = os.path.join(SALIS_ROOT, "notification", "*", "*.json")

JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)
TRANSLATED_LITERAL = re.compile(r"\{\{\s*_\(\s*[\"'](?P<text>[^\"']+)[\"']\s*\)\s*\}\}")
LETTER = re.compile(r"[A-Za-z]")


def shipped_salis_notifications():
    """``[(name, data)]`` for every is_standard Notification the Salis module ships."""
    out = []
    for path in sorted(glob.glob(NOTIFICATION_GLOB)):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("doctype") != "Notification":
            continue
        if not data.get("is_standard"):
            continue
        out.append((os.path.basename(path), data))
    return out


class TestSalisNotificationSubjectLanguage(unittest.TestCase):
    def test_every_subject_puts_its_static_text_through_the_translator(self):
        for filename, data in shipped_salis_notifications():
            with self.subTest(notification=filename):
                subject = data.get("subject") or ""
                residue = JINJA_EXPRESSION.sub("", subject)
                self.assertIsNone(
                    LETTER.search(residue),
                    f"{filename}: the subject carries untranslated text "
                    f"{residue.strip()!r}. Wrap it as "
                    f'{{{{ _("...") }}}} so an Arabic recipient does not read an '
                    f"English subject over an Arabic body.",
                )

    def test_every_subject_names_a_non_empty_string_to_translate(self):
        """A wrapper around nothing would satisfy the residue check and translate nothing."""
        for filename, data in shipped_salis_notifications():
            with self.subTest(notification=filename):
                subject = data.get("subject") or ""
                literals = TRANSLATED_LITERAL.findall(subject)
                self.assertTrue(
                    literals and all(text.strip() for text in literals),
                    f"{filename}: the subject has no non-empty _() literal: {subject!r}",
                )

    def test_the_scan_is_not_silently_empty(self):
        """Guard of the guard: an empty scan passes both assertions vacuously."""
        found = shipped_salis_notifications()
        self.assertGreaterEqual(
            len(found),
            10,
            f"notification scan returned implausibly few files from {SALIS_ROOT}",
        )


if __name__ == "__main__":
    unittest.main()
