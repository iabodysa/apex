# Copyright (c) 2026, AFMCO and contributors
"""The daily SIM watch: who may see which row, and which rows it can see at all.

Two independent defects met in one query. It read every SIM Card on the site and pasted the
MSISDNs into ONE body sent to every SIM Operations User, so a user holding a User Permission
for a single company received the identifiers of every other company's suspended SIMs — the
``permission_query_conditions`` entry that scopes SIM Card cannot save it, because
``frappe.get_all`` hardcodes ``ignore_permissions=True`` (frappe/__init__.py:2050). And it
demanded a live custodian of BOTH statuses, while the custody engine clears the custodian on
a Lost event, so the "lost" half of the watch could never return a row.

Siteless by construction: the SIM table below is data, the scope is stubbed at the module's
own resolver, and nothing is written. That keeps the assertion on the query the task builds
rather than on whatever happens to be seeded on the bench.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from apex.logistay import permissions as logistay_permissions
from apex.logistay.tasks import sim_alerts

CO_A = "AFMCO A"
CO_B = "AFMCO B"

SIMS = [
    {"name": "SIM-A1", "company": CO_A, "status": "Suspended",
     "current_custodian_type": "Employee", "mobile_number": "0500000001"},
    {"name": "SIM-A2", "company": CO_A, "status": "Lost",
     "current_custodian_type": "Unassigned", "mobile_number": "0500000002"},
    {"name": "SIM-A3", "company": CO_A, "status": "Suspended",
     "current_custodian_type": "Unassigned", "mobile_number": "0500000003"},
    {"name": "SIM-B1", "company": CO_B, "status": "Suspended",
     "current_custodian_type": "Employee", "mobile_number": "0599999991"},
]

SCOPED_USER = "scoped@example.com"
OVERSIGHT_USER = "oversight@example.com"


def _matches(row, filters):
    for field, want in filters.items():
        have = row.get(field)
        if isinstance(want, list):
            operator, value = want
            if operator == "in" and have not in value:
                return False
            if operator == "!=" and have == value:
                return False
        elif have != want:
            return False
    return True


class SimWatchCase(unittest.TestCase):
    """The task driven over a constructed SIM table and a constructed company scope."""

    def setUp(self):
        self.sent = []
        self.scope = {}

        def _get_all(doctype, **kwargs):
            if doctype == "Has Role":
                return [SCOPED_USER, OVERSIGHT_USER]
            if doctype == "SIM Card":
                filters = kwargs.get("filters") or {}
                return [
                    frappe._dict({k: row[k] for k in kwargs["fields"]})
                    for row in SIMS
                    if _matches(row, filters)
                ]
            raise AssertionError(f"unexpected read of {doctype}")

        self._start(patch.object(sim_alerts.frappe, "get_all", side_effect=_get_all))
        self._start(patch.object(sim_alerts.frappe.db, "get_value", return_value=1))
        # Stubbed on the permissions module itself, not on the task's own namespace, so
        # the case measures the digest a recipient receives rather than the import the
        # task happens to hold.
        self._start(patch.object(
            logistay_permissions, "report_company_scope",
            side_effect=lambda user, doctype=None: self.scope[user],
        ))
        self._start(patch.object(
            sim_alerts, "notify_user_system",
            side_effect=lambda user, subject, body=None: self.sent.append((user, body or "")),
        ))

    def _start(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, scoped=(CO_A,), oversight=True):
        self.scope = {
            SCOPED_USER: (True, list(scoped)),
            OVERSIGHT_USER: (False, []) if oversight else (True, []),
        }
        sim_alerts.assigned_suspended_or_lost_watch()
        return dict(self.sent)


class TestTheWatchIsScopedToEachRecipient(SimWatchCase):
    def test_a_company_scoped_user_never_sees_another_companys_msisdn(self):
        bodies = self._run()
        self.assertIn("0500000001", bodies[SCOPED_USER])
        self.assertNotIn(
            "0599999991", bodies[SCOPED_USER],
            "a user permitted only company A was handed company B's SIM identifiers",
        )

    def test_an_oversight_recipient_still_sees_every_company(self):
        """The fix must scope, not blank: an unrestricted role keeps the whole estate."""
        bodies = self._run()
        self.assertIn("0500000001", bodies[OVERSIGHT_USER])
        self.assertIn("0599999991", bodies[OVERSIGHT_USER])

    def test_a_scoped_user_holding_no_company_is_not_written_to_at_all(self):
        bodies = self._run(oversight=False)
        self.assertNotIn(
            OVERSIGHT_USER, bodies,
            "a scoped user with no permitted company must receive nothing, not everything",
        )


class TestTheWatchCanActuallyReportALostSim(SimWatchCase):
    def test_a_lost_sim_is_reported_even_though_it_has_no_custodian(self):
        """Retirement clears the custodian, so requiring one excluded every Lost SIM."""
        bodies = self._run()
        self.assertIn(
            "0500000002", bodies[SCOPED_USER],
            "the lost half of the watch returned nothing, which is what it always did",
        )

    def test_an_unheld_suspended_sim_is_still_left_out(self):
        """The custodian condition belongs to the Suspended arm and must survive the fix."""
        bodies = self._run()
        self.assertNotIn("0500000003", bodies[SCOPED_USER])


if __name__ == "__main__":
    unittest.main(verbosity=2)
