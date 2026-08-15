# Copyright (c) 2026, AFMCO and contributors
"""The custody kiosk must not accept a party named after its own DocType.

``frappe.db.exists(dt, dn)`` returns ``dn`` without querying the database when
``dn`` equals ``dt`` (frappe/database/database.py:1259 — the deliberate "a Single
always exists" short-circuit). Both kiosk existence gates rode on that call, so on
a site with no row NAMED ``Employee`` the literal token ``Employee`` passed both:
the scan endpoint echoed a fabricated worker tile, and the write endpoints
accepted it as a recipient. The kiosk scanner is semi-trusted input, so this is a
guard that failed open.

These tests pin the closed behaviour at both live sites:
  * scan — ``resolve_scan`` returns no worker for either literal party type;
  * write — ``get_party_custody`` / ``issue_cart`` / ``return_cart`` refuse it;
and pin that a REAL docname still passes both, so the guard did not close on
legitimate traffic. The refusal is the module's ordinary not-found path, so a
self-named token and a genuinely absent docname are indistinguishable to a caller
probing for rows.
"""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.party_link import (
    PARTY_EMPLOYEE,
    PARTY_TEMPORARY_WORKER,
)
from apex.habitat.api.custody_kiosk import (
    _row_exists,
    get_party_custody,
    issue_cart,
    resolve_scan,
    return_cart,
)

_PARTY_TYPES = (PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestCustodyKioskPartyGuard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        doc = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": "KIOSK-" + _h(),
                "passport_number": "P" + _h(),
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Temporary Worker",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        cls.worker = doc.name

    def setUp(self):
        # The premise, asserted not assumed: no row is NAMED after its DocType.
        # get_value carries no short-circuit, so it reports the table honestly.
        for party_type in _PARTY_TYPES:
            self.assertIsNone(
                frappe.db.get_value(party_type, party_type, "name"),
                "fixture drift: a row named {0} exists, so this guard cannot be "
                "tested on this site".format(party_type),
            )

    def _refusal(self, call) -> str:
        with self.assertRaises(frappe.ValidationError) as caught:
            call()
        return str(caught.exception)

    def test_self_named_token_is_not_a_row(self):
        """The shared helper is the guard, and it refuses without discriminating.

        It returns the SAME verdict for a self-named token as for a docname that
        simply is not there, which is what keeps the refusal from being usable as
        a probe for whether rows exist.
        """
        ghost = "GHOST-" + _h()
        for party_type in _PARTY_TYPES:
            self.assertFalse(_row_exists(party_type, party_type))
            self.assertEqual(
                _row_exists(party_type, party_type),
                _row_exists(party_type, ghost),
            )
        self.assertTrue(_row_exists(PARTY_TEMPORARY_WORKER, self.worker))

    def test_scanning_the_literal_party_type_returns_no_worker(self):
        """Scan site — a badge reading ``Employee`` must not become a tile."""
        for party_type in _PARTY_TYPES:
            for selector in (None, *_PARTY_TYPES):
                result = resolve_scan(party_type, party_type=selector)
                self.assertEqual(
                    result["kind"],
                    "none",
                    "scanning {0!r} with selector {1!r} produced {2!r}".format(
                        party_type, selector, result
                    ),
                )
                self.assertNotIn("party", result)
                self.assertNotIn("party_name", result)

    def test_scanning_a_real_docname_still_returns_the_worker_tile(self):
        """Scan site — the guard must not have closed on legitimate badges."""
        result = resolve_scan(self.worker)
        self.assertEqual(result["kind"], "worker")
        self.assertEqual(result["party_type"], PARTY_TEMPORARY_WORKER)
        self.assertEqual(result["party"], self.worker)
        self.assertEqual(
            result["party_name"],
            frappe.db.get_value("Temporary Worker", self.worker, "worker_name"),
        )

    def test_posting_the_literal_party_type_is_refused(self):
        """Write site — every endpoint that normalizes a party rejects it."""
        for party_type in _PARTY_TYPES:
            calls = (
                lambda pt=party_type: get_party_custody(pt, pt),
                lambda pt=party_type: issue_cart(
                    building="",
                    items_json=json.dumps([{"article": "X", "qty": 1}]),
                    party_type=pt,
                    party=pt,
                ),
                lambda pt=party_type: return_cart(
                    pt, pt, json.dumps([{"custody_issue": "X", "article": "X", "qty": 1}])
                ),
            )
            for call in calls:
                self.assertIn("does not exist", self._refusal(call))

    def test_posting_a_real_docname_still_passes_the_guard(self):
        """Write site — a genuine docname clears the gate and reads its custody."""
        result = get_party_custody(PARTY_TEMPORARY_WORKER, self.worker)
        self.assertEqual(result["party_type"], PARTY_TEMPORARY_WORKER)
        self.assertEqual(result["party"], self.worker)
        self.assertEqual(result["lines"], [])
