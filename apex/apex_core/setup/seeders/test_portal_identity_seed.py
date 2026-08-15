# Copyright (c) 2026, afmcoltd
"""The capacity identity is seeded with its login closed, and converges if it was not.

``simultaneous_sessions = 0`` used to stand for "closed": frappe reads that field as
``... or 1`` (frappe/sessions.py:66) and consults it only when capping concurrent
sessions, so it gated nothing. ``enabled`` is the field the login refuses on
(frappe/auth.py:274-277), and these cases hold the seeder to it — including for an
identity created before the field was set, which the seeder used to skip.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apex.apex_core.setup.seeders import portal_identity_seed as seed


class TestPortalIdentitySeed(unittest.TestCase):
    @patch.object(seed, "_ensure_role")
    @patch.object(seed, "frappe")
    def test_a_new_capacity_user_is_created_with_login_closed(self, frappe_mock, _role):
        frappe_mock.db.exists.return_value = False

        seed.seed_portal_identities()

        payloads = [call.args[0] for call in frappe_mock.get_doc.call_args_list]
        self.assertEqual(len(payloads), len(seed.CAPACITIES))
        for payload in payloads:
            self.assertEqual(payload["enabled"], 0, f"{payload['email']} can still log in")

    @patch.object(seed, "_ensure_role")
    @patch.object(seed, "frappe")
    def test_the_inert_session_cap_is_not_written(self, frappe_mock, _role):
        frappe_mock.db.exists.return_value = False

        seed.seed_portal_identities()

        frappe_mock.db.set_value.assert_not_called()

    @patch.object(seed, "_ensure_role")
    @patch.object(seed, "frappe")
    def test_an_identity_seeded_while_enabled_is_closed_through_the_document(
        self, frappe_mock, _role
    ):
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.get_value.return_value = 1

        seed.seed_portal_identities()

        self.assertEqual(frappe_mock.get_doc.call_count, len(seed.CAPACITIES))
        user = frappe_mock.get_doc.return_value
        self.assertEqual(user.enabled, 0)
        user.save.assert_called()
        # The document, not the column: only User.check_enable_disable ends live sessions.
        frappe_mock.db.set_value.assert_not_called()

    @patch.object(seed, "_ensure_role")
    @patch.object(seed, "frappe")
    def test_an_already_closed_identity_is_left_alone(self, frappe_mock, _role):
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.get_value.return_value = 0

        seed.seed_portal_identities()

        frappe_mock.get_doc.assert_not_called()
