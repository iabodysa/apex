# Copyright (c) 2026, afmcoltd
"""A retried kiosk issue must land once, not twice.

``issue_cart`` submits a Custody Issue whose ``on_submit`` decrements the building store.
With no key naming the cart submission, a retry after a timed-out request submitted a
second issue and decremented the store again — and nothing on the record said the two
were the same handover.

The key is a ``unique`` field on Custody Issue, which is the refusal that actually holds:
the look-up in the endpoint is a snapshot read and two simultaneous retries would both
pass it. The look-up is the ergonomic path; the index is the guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.api import custody_kiosk

DOCTYPE_JSON = (
    Path(custody_kiosk.__file__).resolve().parents[1]
    / "doctype"
    / "custody_issue"
    / "custody_issue.json"
)


def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    fake.parse_json.side_effect = json.loads
    return fake


def _issue(fake, **kwargs):
    endpoint = getattr(custody_kiosk.issue_cart, "__wrapped__", custody_kiosk.issue_cart)
    with (
        patch.object(custody_kiosk, "frappe", fake),
        patch.object(custody_kiosk, "_", side_effect=lambda message: message),
        patch.object(custody_kiosk, "_normalize_party", side_effect=lambda pt, p: (pt, p)),
        patch.object(custody_kiosk, "today", return_value="2026-08-15"),
        patch.object(custody_kiosk, "now_datetime", return_value=None),
    ):
        return endpoint(
            building="BLDG-1",
            items_json='[{"article": "ART-1", "qty": 2}]',
            party_type="Employee",
            party="EMP-1",
            **kwargs,
        )


class TestCustodyIssueCarriesAnIdempotencyKey(TestCase):
    def test_the_key_is_unique_and_never_copied(self):
        meta = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
        field = next(f for f in meta["fields"] if f["fieldname"] == "request_token")

        self.assertTrue(field.get("unique"), "the index is what refuses the second submit")
        self.assertTrue(
            field.get("no_copy"),
            "an amendment or duplicate carrying the key would collide on it",
        )
        self.assertTrue(field.get("read_only"), "the key is the client's, not the form's")

    def test_a_retry_with_the_same_token_returns_the_first_issue(self):
        fake = _raising_frappe()
        fake.db.get_value.return_value = "CUST-ISS-2026-0001"

        result = _issue(fake, request_token="cart-abc")

        self.assertEqual(result, {"custody_issue": "CUST-ISS-2026-0001"})
        fake.get_doc.assert_not_called()
        self.assertEqual(
            fake.db.get_value.call_args.args[:2],
            ("Custody Issue", {"request_token": "cart-abc"}),
        )

    def test_a_first_submission_stores_the_token_on_the_issue(self):
        fake = _raising_frappe()
        fake.db.get_value.return_value = None
        doc = MagicMock()
        doc.name = "CUST-ISS-2026-0002"
        fake.get_doc.return_value = doc

        result = _issue(fake, request_token="cart-abc")

        self.assertEqual(fake.get_doc.call_args.args[0]["request_token"], "cart-abc")
        doc.submit.assert_called_once()
        self.assertEqual(result, {"custody_issue": "CUST-ISS-2026-0002"})

    def test_a_caller_that_sends_no_token_is_still_served(self):
        fake = _raising_frappe()
        doc = MagicMock()
        doc.name = "CUST-ISS-2026-0003"
        fake.get_doc.return_value = doc

        result = _issue(fake)

        self.assertIsNone(
            fake.get_doc.call_args.args[0]["request_token"],
            "an empty token must be NULL, or two tokenless issues collide on the index",
        )
        self.assertEqual(result, {"custody_issue": "CUST-ISS-2026-0003"})
        fake.db.get_value.assert_not_called()


class TestTheDeskPagesSendAToken(TestCase):
    def test_both_desk_callers_pass_a_request_token(self):
        pages = Path(custody_kiosk.__file__).resolve().parents[1] / "page"
        for script in ("custody_kiosk/custody_kiosk.js", "arrivals_desk/arrivals_desk.js"):
            with self.subTest(script=script):
                source = (pages / script).read_text(encoding="utf-8")
                self.assertIn("issue_cart", source)
                self.assertIn(
                    "request_token",
                    source,
                    "a caller that sends no token gets no protection from the retry",
                )
