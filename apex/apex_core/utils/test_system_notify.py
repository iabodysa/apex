# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.system_notify.notify_user_system.

The Notification Log write is mocked, so the disabled-user guard, the unread
dedup, the subject clip, and the optional source-document link are exercised
without a live site.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.apex_core.utils import system_notify


class _FakeDoc:
    def __init__(self, payload):
        self.payload = payload

    def insert(self, *args, **kwargs):
        return self


class TestNotifyUserSystem(unittest.TestCase):
    def test_falsy_user_is_a_noop(self):
        with mock.patch.object(system_notify, "frappe") as mf:
            self.assertFalse(system_notify.notify_user_system(None, "Hi"))
            mf.db.get_value.assert_not_called()

    def test_disabled_user_is_a_noop(self):
        """The ENABLED check is what stops it, so nothing below may run.

        ``frappe`` is a bare mock, so ``db.exists`` answers truthy and the dedup
        branch also returns False: asserting only the False would pass just as well
        with the enabled clause deleted. Pinning the calls below the guard is what
        makes this test able to fail.
        """
        with mock.patch.object(system_notify, "frappe") as mf:
            mf.db.get_value.return_value = 0
            self.assertFalse(system_notify.notify_user_system("u@x", "Hi"))
            mf.db.exists.assert_not_called()
            mf.get_doc.assert_not_called()

    def test_user_who_turned_notifications_off_is_a_noop(self):
        """`User.enabled` answers whether the account may log in, not whether its owner
        wants alerts. Pinning the calls below the guard is what makes this able to fail:
        with the clause deleted the row is inserted and the assertions on get_doc break."""
        with mock.patch.object(system_notify, "frappe") as mf, mock.patch.object(
            system_notify, "is_notifications_enabled", return_value=0
        ):
            mf.db.get_value.return_value = 1
            self.assertFalse(system_notify.notify_user_system("u@x", "Hi"))
            mf.db.exists.assert_not_called()
            mf.get_doc.assert_not_called()

    def test_enabled_user_inserts_alert(self):
        with mock.patch.object(system_notify, "frappe") as mf, mock.patch.object(
            system_notify, "is_notifications_enabled", return_value=1
        ):
            mf.db.get_value.return_value = 1
            mf.db.exists.return_value = False
            captured = {}
            mf.get_doc.side_effect = lambda payload: captured.update(payload) or _FakeDoc(payload)
            self.assertTrue(system_notify.notify_user_system("u@x", "Hello", "Body"))
            self.assertEqual(captured["for_user"], "u@x")
            self.assertEqual(captured["type"], "Alert")
            self.assertEqual(captured["subject"], "Hello")
            self.assertEqual(captured["email_content"], "Body")

    def test_duplicate_unread_alert_is_skipped(self):
        with mock.patch.object(system_notify, "frappe") as mf:
            mf.db.get_value.return_value = 1
            mf.db.exists.return_value = True
            self.assertFalse(system_notify.notify_user_system("u@x", "Hello"))
            mf.get_doc.assert_not_called()

    def test_subject_is_clipped_to_140_chars(self):
        with mock.patch.object(system_notify, "frappe") as mf:
            mf.db.get_value.return_value = 1
            mf.db.exists.return_value = False
            captured = {}
            mf.get_doc.side_effect = lambda payload: captured.update(payload) or _FakeDoc(payload)
            self.assertTrue(system_notify.notify_user_system("u@x", "x" * 200))
            self.assertEqual(len(captured["subject"]), 140)

    def test_source_document_link_added_when_both_present(self):
        with mock.patch.object(system_notify, "frappe") as mf:
            mf.db.get_value.return_value = 1
            mf.db.exists.return_value = False
            captured = {}
            mf.get_doc.side_effect = lambda payload: captured.update(payload) or _FakeDoc(payload)
            self.assertTrue(
                system_notify.notify_user_system(
                    "u@x", "Hi", document_type="Building", document_name="B-1"
                )
            )
            self.assertEqual(captured["document_type"], "Building")
            self.assertEqual(captured["document_name"], "B-1")

    def test_insert_failure_rolls_back_only_this_calls_savepoint(self):
        """This helper is looped per user by every scheduler job that alerts.

        A bare ``frappe.db.rollback()`` here would discard the caller's whole run and
        also DESTROY the per-row savepoint the caller had set, so a later rollback in
        the same iteration would hit MariaDB 1305 uncaught and kill the job. The
        recovery must therefore name this call's own savepoint.
        """
        with mock.patch.object(system_notify, "frappe") as mf:
            mf.db.get_value.return_value = 1
            mf.db.exists.return_value = False
            mf.get_doc.side_effect = RuntimeError("insert failed")
            self.assertFalse(system_notify.notify_user_system("u@x", "Hi"))
            mf.db.savepoint.assert_called_once_with(system_notify._SAVEPOINT)
            mf.db.rollback.assert_called_once_with(save_point=system_notify._SAVEPOINT)
            mf.log_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
