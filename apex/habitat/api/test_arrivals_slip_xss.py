# Copyright (c) 2026, AFMCO and contributors
"""Stored-XSS regression for the Arrivals Desk printed slips.

The desk renders a slip server-side and writes the returned `html` straight into
a new print window (`w.document.write`) -- an unescaped sink. Frappe's Jinja env
is built with autoescape OFF, so any DB free-text field interpolated as `{{ x }}`
reaches that sink raw. The fix is the `| e` filter on every such interpolation in
the three slip templates; this asserts a script payload placed in a field comes
back HTML-entity-encoded, never as a live tag.

These render the actual template objects the whitelisted builders use (same
constants), so a dropped `| e` in any template fails here without needing the
full Employee / Custody Issue master chain."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.arrivals_desk import (
    ARRIVAL_SLIP_TEMPLATE,
    CHECKIN_SLIP_TEMPLATE,
    CUSTODY_HANDOVER_SLIP_TEMPLATE,
)

PAYLOAD = '<img src=x onerror=alert(1)>'
ESCAPED = '&lt;img'
RAW = '<img src=x onerror'


class TestArrivalsSlipXSS(FrappeTestCase):
    def _assert_neutralised(self, html):
        """The payload survives only entity-encoded; the live tag must be gone."""
        self.assertIn(ESCAPED, html, "field value must be HTML-entity-encoded")
        self.assertNotIn(RAW, html, "raw <img ... onerror sink must not appear")
        self.assertNotIn(PAYLOAD, html, "verbatim payload must not reach the document")

    def test_arrival_slip_escapes_db_fields(self):
        """Every identity/housing field on the arrival slip is escaped."""
        ctx = {
            "worker_name": PAYLOAD,
            "party_type_label": PAYLOAD,
            "designation": PAYLOAD,
            "passport_number": PAYLOAD,
            "iqama_number": PAYLOAD,
            "nationality": PAYLOAD,
            "building": PAYLOAD,
            "bed": PAYLOAD,
            "project": PAYLOAD,
            "check_in_date": PAYLOAD,
            "company": PAYLOAD,
            "today": PAYLOAD,
            "dir": "ltr",
            "lang": "en",
            "qr": None,
        }
        self._assert_neutralised(frappe.render_template(ARRIVAL_SLIP_TEMPLATE, ctx))

    def test_checkin_slip_escapes_db_fields(self):
        """Identity, address, city, and housing fields on the check-in slip are escaped."""
        ctx = {
            "worker_name": PAYLOAD,
            "party_type_label": PAYLOAD,
            "building": PAYLOAD,
            "address": PAYLOAD,
            "city": PAYLOAD,
            "bed": PAYLOAD,
            "project": PAYLOAD,
            "check_in_date": PAYLOAD,
            "company": PAYLOAD,
            "today": PAYLOAD,
            "dir": "ltr",
            "lang": "en",
            "terms": [],
        }
        self._assert_neutralised(frappe.render_template(CHECKIN_SLIP_TEMPLATE, ctx))

    def test_custody_slip_escapes_db_fields_and_line_items(self):
        """Header fields and the per-article line items on the custody slip are escaped
		article_name is the attacker-controlled custody field."""
        ctx = {
            "worker_name": PAYLOAD,
            "custody_issue": PAYLOAD,
            "building": PAYLOAD,
            "issue_date": PAYLOAD,
            "company": PAYLOAD,
            "today": PAYLOAD,
            "items": [{"article_name": PAYLOAD, "qty": 1, "uom": PAYLOAD}],
            "show_uom": True,
            "dir": "ltr",
            "lang": "en",
        }
        self._assert_neutralised(frappe.render_template(CUSTODY_HANDOVER_SLIP_TEMPLATE, ctx))

    def test_benign_value_renders_unchanged(self):
        """Escaping does not corrupt a normal plain-text value (no double-encoding)."""
        ctx = {
            "worker_name": "Plain Worker",
            "party_type_label": "Employee",
            "building": "Building A",
            "bed": "Bed 1",
            "project": "Project X",
            "check_in_date": "2026-06-20",
            "company": "Acme",
            "today": "2026-06-27",
            "dir": "ltr",
            "lang": "en",
            "qr": None,
        }
        html = frappe.render_template(ARRIVAL_SLIP_TEMPLATE, ctx)
        self.assertIn("Plain Worker", html)
        self.assertIn("Building A", html)
        self.assertNotIn("&amp;", html, "a clean value must not be double-escaped")
