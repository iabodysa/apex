# Copyright (c) 2026, AFMCO and contributors
"""Tests for the linked-worker custody re-point patch's OWN logic: which
Temporary Workers it replays ``_repoint_party`` over.

``_repoint_party`` itself is tested directly at
``apex.habitat.test_temporary_worker_party_repoint``; what belongs to this
patch is its selection -- only a worker whose status is Linked AND who carries
a ``linked_employee`` -- so ``_repoint_party`` is mocked here to isolate that
filter from its own internals.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6.repoint_linked_worker_custody_party import execute


def _h():
    return frappe.generate_hash(length=12).upper()


def _worker(status, linked_employee=None):
    doc = frappe.get_doc(
        {
            "doctype": "Temporary Worker",
            "worker_name": "TW-" + _h(),
            "passport_number": "P" + _h(),
            "status": status,
            "linked_employee": linked_employee,
        }
    )
    doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
    return doc.name


class TestRepointLinkedWorkerCustodyPartySelection(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self._names = []

    def tearDown(self):
        for name in self._names:
            frappe.delete_doc("Temporary Worker", name, ignore_permissions=True, force=True)

    def test_only_linked_workers_with_an_employee_are_replayed(self):
        linked = _worker("Linked", self.employee)
        self._names.append(linked)
        unlinked_no_employee = _worker("Active")
        self._names.append(unlinked_no_employee)
        linked_no_employee = _worker("Linked")
        self._names.append(linked_no_employee)

        with patch(
            "apex.patches.v2_6.repoint_linked_worker_custody_party._repoint_party"
        ) as repoint:
            execute()

        called_with = [call.args for call in repoint.call_args_list]
        self.assertIn((linked, self.employee), called_with)
        self.assertEqual(
            len([c for c in called_with if c[0] in (unlinked_no_employee, linked_no_employee)]),
            0,
        )
