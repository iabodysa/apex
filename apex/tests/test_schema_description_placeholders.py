# Copyright (c) 2026, AFMCO and contributors
"""Guard: a shipped DocType ``description`` must not carry a format placeholder.

A description is body text Frappe renders VERBATIM under the input, or in the
list-view empty state — nothing ever calls ``.format()`` on it, so a ``{0}`` left
in one reaches the operator unfilled, in every language and on every install.
A placeholder belongs at a ``_()`` call site, which is given arguments to fill it.
"""

import glob
import json
import re

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex")


def _descriptions():
    """Yield (relative schema path, fieldname, description) for every shipped DocType.

    A fieldname of None is the DocType's own description, which list_view.js renders
    in the empty state and so reaches the operator just as directly."""
    for path in sorted(glob.glob(f"{APP}/**/doctype/*/*.json", recursive=True)):
        try:
            payload = json.loads(open(path, encoding="utf-8").read())
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("doctype") != "DocType":
            continue
        rel = path[len(APP) + 1:]
        own = payload.get("description")
        if isinstance(own, str) and own.strip():
            yield rel, None, own.strip()
        for field in payload.get("fields") or []:
            if not isinstance(field, dict):
                continue
            text = field.get("description")
            if isinstance(text, str) and text.strip():
                yield rel, field.get("fieldname"), text.strip()


class TestSchemaDescriptionPlaceholders(FrappeTestCase):
    def test_descriptions_carry_no_static_placeholder(self):
        """A description renders verbatim, so an unfilled {0} would reach the user."""
        braced = sorted(
            f"{rel}:{fieldname or '<doctype>'}"
            for rel, fieldname, text in _descriptions()
            if re.search(r"\{\d+\}", text)
        )
        self.assertEqual(braced, [], f"descriptions with a format placeholder: {braced}")
