# Copyright (c) 2026, AFMCO and contributors
"""The kiosk's article scan must reach the database, and keep its name fallback.

``_resolve_article_scan`` tries the scanned token as a Custody Article DOCNAME
first and, only when that misses, as a unique ``article_name``. The docname probe
was the one gate in this module still calling ``frappe.db.exists`` positionally,
which answers the value back WITHOUT a query when it equals the DocType
(database.py:1259 — the "a Single always exists" short-circuit).

LATENT, not live. The token ``Custody Article`` took the docname branch it should
not have, but ``get_value`` then returned ``None`` and the scan degraded into a
benign miss — no fabricated tile, no write. What it actually cost was the
``article_name`` fallback, which sits in the ``else`` arm and therefore never ran
for that token: an article TITLED "Custody Article" was unfindable by scan. This is
consistency work, not a closed hole.

The fix routes the probe through ``_row_exists``, the shared helper the two party
gates already use, so the whole module now carries ONE existence idiom — the dict
filter (database.py:1253-1257), which cannot short-circuit and is correct in both
directions. ``_row_exists`` itself moved off its earlier ``name != doctype``
rejection, which only traded the false positive for a false negative.

Site-free: only ``frappe.db.exists`` decides these paths, so the module's ``frappe``
is swapped for a stub that reproduces the short-circuit faithfully.
"""

import unittest
from unittest.mock import patch

from apex.habitat.api import custody_kiosk

ARTICLE_DOCTYPE = "Custody Article"
PARTY_DOCTYPE = "Employee"


class _StubDB:
    """``frappe.db``, faithful to database.py:1259 on the positional call shape."""

    def __init__(self, rows):
        self.rows = rows
        self.queried = []

    def exists(self, doctype, key):
        if isinstance(key, str) and key == doctype and doctype != "DocType":
            return key
        self.queried.append((doctype, key))
        names = {row["name"] for row in self.rows.get(doctype, [])}
        if isinstance(key, dict):
            return next((value for value in key.values() if value in names), None)
        return key if key in names else None

    def get_value(self, doctype, name, fields, as_dict=False):
        for row in self.rows.get(doctype, []):
            if row["name"] == name:
                return dict(row)
        return None


class _StubFrappe:
    def __init__(self, rows):
        self.db = _StubDB(rows)
        self.get_all_calls = []

    def has_permission(self, *_args, **_kwargs):
        return True

    def get_all(self, doctype, filters=None, fields=None, limit=None):
        self.get_all_calls.append((doctype, dict(filters or {})))
        wanted = (filters or {}).get("article_name")
        matched = [dict(r) for r in self.db.rows.get(doctype, []) if r.get("article_name") == wanted]
        return matched[:limit] if limit else matched


def _article(name, article_name):
    return {
        "name": name,
        "article": name,
        "article_name": article_name,
        "unit_of_measure": "Nos",
        "uom": "Nos",
        "image": None,
        "standard_unit_cost": 0,
    }


def _scan(code, rows):
    stub = _StubFrappe(rows)
    with patch.object(custody_kiosk, "frappe", stub):
        return custody_kiosk._resolve_article_scan(code, None), stub


class TestTheArticleNameFallbackIsStillConsulted(unittest.TestCase):
    def test_the_literal_doctype_string_reaches_the_article_name_fallback(self):
        """The recorded defect. An article TITLED "Custody Article" was unreachable
        because the short-circuited docname branch swallowed the token before the
        fallback could run."""
        titled = _article("CA-2026-00007", ARTICLE_DOCTYPE)
        result, stub = _scan(ARTICLE_DOCTYPE, {ARTICLE_DOCTYPE: [titled]})
        self.assertEqual(
            stub.get_all_calls,
            [(ARTICLE_DOCTYPE, {"article_name": ARTICLE_DOCTYPE})],
            "the article_name fallback must be consulted for a self-named token",
        )
        self.assertIsNotNone(result, "the titled article must be found by scan")
        self.assertEqual(result["kind"], "article")
        self.assertEqual(result["article"]["article"], "CA-2026-00007")

    def test_the_literal_doctype_string_alone_still_matches_nothing(self):
        """No fabricated tile when nothing bears that docname or title."""
        result, stub = _scan(ARTICLE_DOCTYPE, {ARTICLE_DOCTYPE: [_article("CA-1", "Blanket")]})
        self.assertIsNone(result)
        self.assertTrue(stub.get_all_calls, "the fallback must still have been consulted")

    def test_a_real_docname_still_takes_the_docname_branch(self):
        """The guard did not close on legitimate scans: a docname match short-cuts
        the fallback exactly as before."""
        result, stub = _scan("CA-2026-00001", {ARTICLE_DOCTYPE: [_article("CA-2026-00001", "Mat")]})
        self.assertEqual(result["article"]["article"], "CA-2026-00001")
        self.assertEqual(stub.get_all_calls, [], "a docname hit must not run the fallback")

    def test_an_ambiguous_title_is_still_refused(self):
        rows = [_article("CA-1", "Blanket"), _article("CA-2", "Blanket")]
        result, _stub = _scan("Blanket", {ARTICLE_DOCTYPE: rows})
        self.assertIsNone(result, "a non-unique title must stay the operator's choice")


class TestTheSharedExistenceHelperIsCorrectBothWays(unittest.TestCase):
    """``_row_exists`` is now the single idiom for every gate in this module, so it
    must be right in both directions — not merely closed."""

    def _exists(self, doctype, name, rows):
        stub = _StubFrappe(rows)
        with patch.object(custody_kiosk, "frappe", stub):
            return custody_kiosk._row_exists(doctype, name), stub

    def test_a_self_named_token_with_no_row_behind_it_is_false(self):
        found, stub = self._exists(PARTY_DOCTYPE, PARTY_DOCTYPE, {PARTY_DOCTYPE: []})
        self.assertFalse(found)
        self.assertTrue(stub.db.queried, "the probe must reach the database, not short-circuit")

    def test_a_row_really_named_after_its_doctype_is_true(self):
        """The direction a bare ``name != doctype`` rejection got wrong."""
        rows = {PARTY_DOCTYPE: [{"name": PARTY_DOCTYPE}]}
        found, _stub = self._exists(PARTY_DOCTYPE, PARTY_DOCTYPE, rows)
        self.assertTrue(found)

    def test_an_ordinary_absent_docname_is_false(self):
        found, _stub = self._exists(PARTY_DOCTYPE, "HR-EMP-00001", {PARTY_DOCTYPE: []})
        self.assertFalse(found)

    def test_an_ordinary_present_docname_is_true(self):
        rows = {PARTY_DOCTYPE: [{"name": "HR-EMP-00001"}]}
        found, _stub = self._exists(PARTY_DOCTYPE, "HR-EMP-00001", rows)
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
