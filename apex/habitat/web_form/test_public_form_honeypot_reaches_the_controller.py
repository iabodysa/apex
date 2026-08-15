# Copyright (c) 2026, afmcoltd
"""The honeypot has to sit where the live form actually saves.

Both public Habitat web forms ship a hidden ``website_field``, and both hardened
``submit_*`` endpoints reject a filled one. But the forms themselves post to Frappe's
own ``web_form.accept``, which copies every declared web form field onto the document
(frappe/website/doctype/web_form/web_form.py:632-647) and inserts it — the ``submit_*``
endpoint is never on that path. The trap only catches anything once the controller
reads it.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.arrival_batch import arrival_batch
from apex.habitat.doctype.resident_request import resident_request

APP_ROOT = Path(__file__).resolve().parents[1]

_FORMS = {
    "accommodation_resident_request": "Resident Request",
    "arrival_manifest": "Arrival Batch",
}


def _raising_frappe() -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake


class TestBothPublicFormsShipTheHoneypot(TestCase):
    def test_the_hidden_field_is_still_on_both_live_forms(self):
        for form, doctype in _FORMS.items():
            with self.subTest(form=form):
                meta = json.loads(
                    (APP_ROOT / "web_form" / form / f"{form}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(meta["doc_type"], doctype)
                self.assertIn(
                    "website_field",
                    {field["fieldname"] for field in meta["web_form_fields"]},
                    "the trap has to be offered before it can be sprung",
                )


class TestTheControllerRefusesAFilledHoneypot(TestCase):
    def test_resident_request_refuses_before_it_resolves_anything(self):
        doc = MagicMock()
        doc.get.side_effect = lambda key, *_a, **_kw: (
            "http://spam.example" if key == "website_field" else None
        )
        fake = _raising_frappe()

        with (
            patch.object(resident_request, "frappe", fake),
            patch.object(resident_request, "_", side_effect=lambda message: message),
            patch.object(resident_request, "_populate_location_from_token") as populate,
        ):
            with self.assertRaises(frappe.PermissionError):
                resident_request.validate(doc)

        populate.assert_not_called()

    def test_arrival_batch_refuses_before_it_counts_anything(self):
        doc = MagicMock(expected_workers=[MagicMock()], expected_count=None, title=None)
        doc.get.side_effect = lambda key, *_a, **_kw: (
            "http://spam.example" if key == "website_field" else None
        )
        fake = _raising_frappe()

        with (
            patch.object(arrival_batch, "frappe", fake),
            patch.object(arrival_batch, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.PermissionError):
                arrival_batch.ArrivalBatch.validate(doc)

        self.assertIsNone(doc.expected_count)

    def test_an_empty_honeypot_lets_the_save_continue(self):
        doc = MagicMock(location_token=None)
        doc.get.side_effect = lambda key, *_a, **_kw: None
        fake = _raising_frappe()

        with (
            patch.object(resident_request, "frappe", fake),
            patch.object(resident_request, "_", side_effect=lambda message: message),
            patch.object(resident_request, "_populate_location_from_token") as populate,
            patch.object(resident_request, "sync_party_employee"),
            patch.object(resident_request, "_validate_status_transition"),
        ):
            resident_request.validate(doc)

        populate.assert_called_once()
