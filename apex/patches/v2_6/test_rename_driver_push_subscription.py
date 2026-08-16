# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Driver Push Subscription -> Portal Push Subscription rename
patch's already-gone guard.

The old DocType is gone on every current site (the rename already ran), so
that no-op branch is the one every real run of this patch takes and the one
pinned here. The "both names exist -> refuse" branch is deliberately NOT
exercised: proving it needs a real DocType under the old name, and creating
one issues DDL (CREATE/DROP TABLE) that a per-test rollback cannot undo on a
shared site -- a defect class this suite must not risk to cover a guard on a
patch that has already completed its one-time migration everywhere.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6.rename_driver_push_subscription import OLD_DOCTYPE, execute


class TestRenameDriverPushSubscriptionGuard(FrappeTestCase):
    def test_noop_when_the_old_doctype_is_already_gone(self):
        self.assertFalse(frappe.db.exists("DocType", OLD_DOCTYPE))
        execute()  # must not raise
