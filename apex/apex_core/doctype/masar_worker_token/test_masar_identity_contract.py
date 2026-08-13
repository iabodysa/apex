from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    resolve_driver_token,
)
from apex.apex_core.utils import portal_token_security as security


class TestMasarIdentityContract(TestCase):
    @patch.object(security, "_throttle_bad_token_attempt")
    @patch.object(security.frappe.db, "get_value")
    def test_worker_and_driver_tokens_are_audience_exclusive(
        self, get_value, _throttle
    ):
        get_value.return_value = None

        with self.assertRaises(frappe.PermissionError):
            security.resolve_portal_subject(
                security.DRIVER, "worker-token", required=True
            )

        token_filters = get_value.call_args.args[1]
        self.assertEqual(token_filters["holder_type"], security.DRIVER)
        self.assertEqual(token_filters["enabled"], 1)

    @patch.object(security, "presented_token", return_value=("", False))
    def test_salis_session_is_not_a_driver_bearer_credential(self, _presented):
        self.assertIsNone(resolve_driver_token())

    def test_binding_rejects_mixed_worker_and_driver_subjects(self):
        row = frappe._dict(
            holder_type="Worker",
            party_type="Employee",
            party="EMP-1",
            employee="EMP-1",
            driver="DRV-1",
        )
        with self.assertRaises(frappe.PermissionError):
            security.validate_subject_binding(
                row, security.WORKER, exception=frappe.PermissionError
            )

    @patch.object(security, "_throttle_bad_token_attempt")
    @patch.object(security.frappe.db, "get_value")
    def test_expired_token_fails_closed(self, get_value, _throttle):
        get_value.return_value = frappe._dict(
            holder_type="Worker",
            party_type="Employee",
            party="EMP-1",
            employee="EMP-1",
            driver=None,
            expires_on="2000-01-01 00:00:00",
        )
        with self.assertRaises(frappe.PermissionError):
            security.resolve_portal_subject(security.WORKER, "expired", required=True)

    def test_revocation_disables_the_subjects_notification_devices(self):
        with (
            patch.object(security, "_lock_subject_row", return_value=frappe._dict(name="EMP-1")),
            patch.object(
                security,
                "_lock_subject_token_rows",
                return_value=[frappe._dict(name="TOKEN-1", enabled=1)],
            ),
            patch.object(security, "log_credential_event"),
            patch.object(security.frappe.db, "set_value"),
            patch.object(security.frappe.db, "table_exists", return_value=True),
            patch("apex.salis.api.web_push.disable_subject_subscriptions") as disable,
        ):
            self.assertEqual(security.revoke_subject_tokens(security.WORKER, "EMP-1"), 1)

        disable.assert_called_once_with(security.WORKER, "EMP-1")
