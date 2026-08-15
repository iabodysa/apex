# Copyright (c) 2026, AFMCO and contributors
"""Every Dispatch Trip a boarding endpoint saves is loaded under its own row lock.

Four boarding writers took a ``SELECT … FOR UPDATE`` on the trip row before touching it.
Six more in the same module loaded the whole trip, mutated ``boarding_state`` and saved,
with no lock at all — among them a poll running at 120 requests a minute.

What that costs was MEASURED here rather than assumed, and it is smaller than it looks.
Saving a Dispatch Trip does rewrite ``boarding_state`` wholesale — ``validate`` re-syncs
the manifest, so the rows reaching ``update_children`` carry no names and the child table
is emptied and re-inserted from the saver's own copy — but the framework refuses the save
before that happens: ``check_if_latest`` compares the caller's ``modified`` against a
locking read of the stored row and raises ``TimestampMismatchError``. A worker who has
just self-confirmed is therefore NOT silently reverted to Pending.

What contention actually costs is the driver's tap. At the stop, while workers are
confirming, "notify remaining" and the not-boarded override are rejected with a timestamp
mismatch and simply do not apply. The lock turns that into a wait: the second caller
blocks, then reads the row as the first left it, and its write lands.

The lock now sits at the LOAD (``boarding_flow._locked_trip``) rather than at each
endpoint, so a writer added later cannot be the one that forgets it, and it is passed to
the load rather than taken beside it — on MariaDB at REPEATABLE READ a lock taken before
a plain read does not advance the transaction's read view.
"""

from __future__ import annotations

import ast

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import boarding_flow

test_dependencies = ["Employee"]


class TestAStaleTripSaveIsRefusedNotMerged(FrappeTestCase):
    """The measurement behind the lock: what a stale snapshot actually does on save."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.trip = self._trip()

    def _trip(self):
        doc = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_date": frappe.utils.today(),
                "status": "Planned",
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Dispatch Trip", doc.name, force=True, ignore_permissions=True
        )
        doc.append(
            "boarding_state",
            {"employee": self.employee, "status": "Pending", "notify_count": 0, "wait_count": 0},
        )
        doc.save(ignore_permissions=True)
        return doc.name

    def _status(self):
        return frappe.db.get_value(
            "Trip Boarding State",
            {"parent": self.trip, "employee": self.employee},
            "status",
        )

    def test_a_stale_trip_save_is_refused_and_the_confirm_survives(self):
        """Two documents, both loaded before either wrote. The second save is refused —
        so the reported silent revert to Pending does not happen, and the real cost is
        the refused write, which is what the lock removes."""
        stale = frappe.get_doc("Dispatch Trip", self.trip)

        fresh = frappe.get_doc("Dispatch Trip", self.trip)
        fresh.boarding_state[0].status = "Boarded"
        fresh.boarding_state[0].confirm_source = "Worker"
        fresh.save(ignore_permissions=True)
        self.assertEqual(self._status(), "Boarded", "the worker's own confirm did not land")

        stale.boarding_state[0].notify_count = 1
        with self.assertRaises(frappe.TimestampMismatchError):
            stale.save(ignore_permissions=True)

        self.assertEqual(
            self._status(),
            "Boarded",
            "the worker's confirm was rewritten by a snapshot that never saw it",
        )

    def test_the_locking_load_reads_the_row_rather_than_this_transaction_s_snapshot(self):
        """The half the lock is actually for. ``_locked_trip`` must build the document
        from a locking read, not from a view pinned earlier in the request."""
        loaded = boarding_flow._locked_trip(self.trip)

        self.assertTrue(
            loaded.flags.for_update,
            "the trip was loaded with plain reads, so its snapshot may predate the lock",
        )
        self.assertEqual(loaded.name, self.trip)


class TestEveryTripLoadTakesTheLock(FrappeTestCase):
    """The structural rule, read off the shipped source rather than argued."""

    def test_no_endpoint_loads_a_dispatch_trip_outside_the_locking_helper(self):
        with open(boarding_flow.__file__, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)

        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "get_doc"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != "Dispatch Trip":
                continue
            offenders.append(node.lineno)

        self.assertEqual(
            offenders,
            [self._helper_line()],
            "a Dispatch Trip is loaded outside _locked_trip at these lines; every load "
            "this module saves must hold the row first",
        )

    @staticmethod
    def _helper_line():
        """The one sanctioned load — inside ``_locked_trip`` itself."""
        with open(boarding_flow.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        helper = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_locked_trip"
        )
        return next(
            n.lineno
            for n in ast.walk(helper)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_doc"
        )

    def test_the_one_sanctioned_load_is_the_locking_one(self):
        """Guard of the guard: a ``_locked_trip`` that dropped ``for_update`` would leave
        the rule above satisfied and every writer reading an unlocked snapshot."""
        with open(boarding_flow.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        helper = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_locked_trip"
        )
        load = next(
            n
            for n in ast.walk(helper)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_doc"
        )
        self.assertTrue(
            any(
                kw.arg == "for_update" and getattr(kw.value, "value", None) is True
                for kw in load.keywords
            ),
            "_locked_trip loads the trip without for_update, so neither the parent row "
            "nor the boarding rows are locked and the read may predate the write",
        )
