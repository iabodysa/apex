# Copyright (c) 2026, afmcoltd
"""Every refusal inside ``acknowledge_intercompany_movement``, and the button that reaches it.

The endpoint carries four rules, not one: permlevel-1 write on the flag, a submitted
document, an intercompany movement, and the separation of duties that stops the submitter
signing off their own transfer. A mock that asserts only that two permission methods were
CALLED lets the docstatus and intercompany refusals each be deleted whole with the suite
green, so ``TestEveryAcknowledgementRefusalIsExercised`` below drives every refusal by its
actual outcome (a raised exception, an untouched ``db_set``) instead.

``TestFacilityAssetMovementAcknowledgement`` grades the same two permission primitives at a
coarser level — patching ``frappe.get_doc`` / ``frappe.get_roles`` / ``frappe.session``
directly rather than replacing the endpoint module's whole ``frappe`` — so a change to which
permission call the endpoint makes is caught here too, independent of the outcome-level
refusals above.

It also has to be reachable. The Number Card publishes the queue of movements waiting for
this sign-off; with no client caller the only way to clear that queue was a hand-written
API call, so the queue only ever counted up.

Every class in this module is a pure mock of ``acknowledge_intercompany_movement`` — no
database record is ever created. The DB-backed grading of the same endpoint (a real
submitted, intercompany Facility Asset Movement, a real accountant) lives in
``test_facility_asset_movement_acknowledgement.py`` beside this file.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.facility_asset_movement import facility_asset_movement

ENDPOINT = "acknowledge_intercompany_movement"


def _raising_frappe(user="accountant@example.com") -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError
    fake.session = SimpleNamespace(user=user)

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake


def _movement(**overrides):
    movement = MagicMock()
    movement.name = "MOVE-1"
    movement.docstatus = 1
    movement.is_intercompany = 1
    movement.owner = "preparer@example.com"
    movement.accounting_acknowledged = 0
    movement.has_permlevel_access_to.return_value = True
    for key, value in overrides.items():
        setattr(movement, key, value)
    return movement


def _call(movement, user="accountant@example.com"):
    fake = _raising_frappe(user)
    fake.get_doc.return_value = movement
    endpoint = getattr(facility_asset_movement, ENDPOINT)
    with (
        patch.object(facility_asset_movement, "frappe", fake),
        patch.object(facility_asset_movement, "_", side_effect=lambda message: message),
    ):
        return getattr(endpoint, "__wrapped__", endpoint)("MOVE-1")


class TestEveryAcknowledgementRefusalIsExercised(TestCase):
    def test_an_unsubmitted_movement_is_refused(self):
        for docstatus in (0, 2):
            with self.subTest(docstatus=docstatus):
                movement = _movement(docstatus=docstatus)
                with self.assertRaises(frappe.ValidationError):
                    _call(movement)
                movement.db_set.assert_not_called()

    def test_a_same_company_movement_is_refused(self):
        movement = _movement(is_intercompany=0)
        with self.assertRaises(frappe.ValidationError):
            _call(movement)
        movement.db_set.assert_not_called()

    def test_the_submitter_cannot_sign_off_their_own_movement(self):
        movement = _movement(owner="preparer@example.com")
        with self.assertRaises(frappe.PermissionError):
            _call(movement, user="preparer@example.com")
        movement.db_set.assert_not_called()

    def test_a_permitted_accountant_signs_off_and_the_record_names_them(self):
        movement = _movement()
        result = _call(movement)

        movement.db_set.assert_called_once_with(
            {
                "accounting_acknowledged": 1,
                "accounting_acknowledged_by": "accountant@example.com",
            },
            update_modified=True,
        )
        self.assertEqual(result["acknowledged_by"], "accountant@example.com")

    def test_a_repeat_call_writes_nothing_further(self):
        movement = _movement(
            accounting_acknowledged=1, accounting_acknowledged_by="first@example.com"
        )
        result = _call(movement)

        movement.db_set.assert_not_called()
        self.assertEqual(result["acknowledged_by"], "first@example.com")


class TestTheSignOffIsReachableFromTheForm(TestCase):
    def test_the_form_script_calls_the_endpoint(self):
        script = (
            Path(__file__).with_name("facility_asset_movement.js").read_text(encoding="utf-8")
        )
        self.assertIn(
            ENDPOINT,
            script,
            "with no client caller the pending-acknowledgement queue can only count up",
        )
        self.assertIn(
            "add_custom_button",
            script,
            "the endpoint needs a control on the form, not just a name in a string",
        )


class TestFacilityAssetMovementAcknowledgement(TestCase):
    """Coarser-grained mock of the same endpoint: patches the two permission
    primitives directly on the module's real ``frappe`` object rather than
    replacing ``frappe`` wholesale, so a change to which permission call the
    endpoint makes shows up here independent of the outcome-level refusals above."""

    def test_acknowledgement_uses_document_and_field_permissions(self):
        movement = MagicMock()
        movement.name = "MOVE-1"
        movement.docstatus = 1
        movement.is_intercompany = 1
        movement.owner = "preparer@example.com"
        movement.accounting_acknowledged = 0
        movement.has_permlevel_access_to.return_value = True

        with (
            patch.object(facility_asset_movement.frappe, "get_doc", return_value=movement),
            patch.object(
                facility_asset_movement.frappe,
                "get_roles",
                return_value=["Finance Manager"],
            ),
            patch.object(
                facility_asset_movement.frappe,
                "session",
                SimpleNamespace(user="accountant@example.com"),
            ),
        ):
            facility_asset_movement.acknowledge_intercompany_movement("MOVE-1")

        movement.check_permission.assert_called_once_with("read")
        movement.has_permlevel_access_to.assert_called_once_with(
            "accounting_acknowledged",
            permission_type="write",
        )

    def test_acknowledgement_rejects_field_without_write_permission(self):
        movement = MagicMock()
        movement.name = "MOVE-1"
        movement.docstatus = 1
        movement.is_intercompany = 1
        movement.owner = "preparer@example.com"
        movement.accounting_acknowledged = 0
        movement.has_permlevel_access_to.return_value = False

        with (
            patch.object(facility_asset_movement.frappe, "get_doc", return_value=movement),
            patch.object(
                facility_asset_movement.frappe,
                "session",
                SimpleNamespace(user="accountant@example.com"),
            ),
            self.assertRaises(frappe.PermissionError),
        ):
            facility_asset_movement.acknowledge_intercompany_movement("MOVE-1")

        movement.db_set.assert_not_called()
