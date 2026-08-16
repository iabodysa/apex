# Copyright (c) 2026, AFMCO and contributors
"""``link_temporary_workers`` must roll back only the worker that failed.

The daily linker walks every Active Temporary Worker and CONTINUES past a row
that raises. It recovers with ``frappe.db.rollback(save_point=...)``: the same
per-row isolation ``salis/fuel_engine.py`` and ``salis/rental_engine.py`` use. A bare
``frappe.db.rollback()`` instead takes no savepoint and would discard the WHOLE
transaction — every worker already linked earlier in the same run would lose its
link, and one bad passport would throw away the run's good work.

Two properties, one per test: a worker linked BEFORE the failure keeps its link,
and a worker reached AFTER the failure is still linked. Both also assert the
failed worker itself is left clean — its own write is what the savepoint undoes.

The engine's Temporary Worker page query is narrowed to this test's own rows.
That is isolation, not convenience: a pre-existing Active worker on the site would
drag the run through unrelated modules and make a failure there look like a failure
here.

``TestTemporaryWorkerPagingReachesEveryWorker`` covers the other way this loop lost
work. It pages over ``status = Active`` while ``_link`` flips that same status to
Linked, so rows left the result set under an advancing OFFSET cursor and everything
that shifted down was skipped — silently, with no error anywhere. It seeds more
workers than fit in one page and asserts every one is reached. Shrinking the page
size rather than seeding 500 rows is what makes that assertion affordable.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

import apex.habitat.temporary_worker_engine as engine


def _h():
    return frappe.generate_hash(length=12).upper()


def _pair():
    """One Temporary Worker plus the Active Employee its passport matches."""
    passport = "P" + _h()
    emp = frappe.get_doc({
        "doctype": "Employee",
        "first_name": "EMP-" + _h(),
        "naming_series": "HR-EMP-",
        "passport_number": passport,
        "status": "Active",
    })
    emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
    tw = frappe.get_doc({
        "doctype": "Temporary Worker",
        "worker_name": "TW-" + _h(),
        "passport_number": passport,
        "status": "Active",
    })
    tw.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
    return tw.name, emp.name


class TestTemporaryWorkerLinkLoopResilience(FrappeTestCase):
    """One failing worker must not discard the workers linked around it."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.pairs = dict([_pair(), _pair()])
        self.mine = set(self.pairs)

    def _run(self, fail_at):
        """Drive the daily linker over this test's two workers, raising on the
        ``fail_at``-th one (1-based) AFTER it has written. Returns the order reached."""
        reached = []
        real_get_all = frappe.get_all
        real_link = engine._link
        mine = self.mine

        def _only_these_workers(doctype, *args, **kwargs):
            if doctype != "Temporary Worker":
                return real_get_all(doctype, *args, **kwargs)
            if kwargs.get("limit_start"):
                return []
            unpaged = dict(kwargs, limit_start=0, limit_page_length=0)
            return [r for r in real_get_all(doctype, *args, **unpaged) if r.name in mine]

        def _link_or_fail(tw, employee):
            reached.append(tw.name)
            if len(reached) != fail_at:
                return real_link(tw, employee)
            # A real write BEFORE the raise: the savepoint has to UNDO this row, not
            # merely spare its siblings.
            frappe.db.set_value("Temporary Worker", tw.name, "linked_employee", employee)
            raise frappe.ValidationError("injected link failure")

        with patch.object(engine.frappe, "get_all", side_effect=_only_these_workers), \
                patch.object(engine, "_link", side_effect=_link_or_fail):
            engine.link_temporary_workers()

        self.assertEqual(
            len(reached), 2,
            "Both workers must be reached - the loop has to continue past the failure.",
        )
        return reached

    def _assert_linked(self, worker, why):
        self.assertEqual(frappe.db.get_value("Temporary Worker", worker, "status"), "Linked", why)
        self.assertEqual(
            frappe.db.get_value("Temporary Worker", worker, "linked_employee"),
            self.pairs[worker],
            why,
        )

    def _assert_untouched(self, worker):
        self.assertEqual(
            frappe.db.get_value("Temporary Worker", worker, "status"), "Active",
            "The failed worker must stay Active so the next run retries it.",
        )
        self.assertFalse(
            frappe.db.get_value("Temporary Worker", worker, "linked_employee"),
            "The failed worker's own write must be rolled back to the savepoint.",
        )

    def test_second_worker_failure_keeps_the_first_worker_linked(self):
        first, second = self._run(fail_at=2)
        self._assert_linked(
            first,
            "The FIRST worker's link must survive the second worker's failure - a bare "
            "frappe.db.rollback() discarded it along with the whole transaction.",
        )
        self._assert_untouched(second)

    def test_worker_after_a_failing_one_is_still_linked(self):
        first, second = self._run(fail_at=1)
        self._assert_linked(
            second,
            "A worker reached AFTER a failing one must still be linked - the loop "
            "continues, and the failure rolls back only its own row.",
        )
        self._assert_untouched(first)


class TestTemporaryWorkerPagingReachesEveryWorker(FrappeTestCase):
    """More Active workers than fit in one page must ALL be reached in one run.

    The page size is shrunk instead of seeding 500 workers, so the loop really runs
    several pages. The harness narrows the result to this test's own rows but keeps
    every part of the engine's query — its status filter, its name cursor, its
    ordering and its page length — so the paging under test stays the engine's.
    """

    PAGE = 2
    WORKERS = 5  # 3 pages at PAGE=2, so a skip cannot hide in a single boundary

    def setUp(self):
        frappe.set_user("Administrator")
        self.pairs = dict(_pair() for _ in range(self.WORKERS))
        self.mine = set(self.pairs)

    def _run(self):
        """Drive the real linker over this test's workers at a 2-row page size."""
        real_get_all = frappe.get_all
        mine = self.mine
        pages = []

        def _only_mine(doctype, *args, **kwargs):
            if doctype != "Temporary Worker":
                return real_get_all(doctype, *args, **kwargs)
            # Apply the engine's OWN filters over an unpaged read, then take its page
            # off this test's rows: a foreign Active worker must not consume a slot,
            # or the harness would fabricate the very skip it is looking for.
            unpaged = dict(kwargs, limit_start=0, limit_page_length=0)
            rows = [r for r in real_get_all(doctype, *args, **unpaged) if r.name in mine]
            rows = rows[: kwargs.get("limit_page_length") or len(rows)]
            pages.append([r.name for r in rows])
            return rows

        with patch.object(engine, "_BATCH_SIZE", self.PAGE), \
                patch.object(engine.frappe, "get_all", side_effect=_only_mine):
            engine.link_temporary_workers()
        return pages

    def test_every_active_worker_is_linked_across_pages(self):
        pages = self._run()

        self.assertGreater(
            len(pages), 1,
            "the harness collapsed the run into one page, so it cannot see a paging skip",
        )
        self.assertTrue(
            all(len(p) <= self.PAGE for p in pages),
            f"the engine ignored its page size, so these are not real pages: {pages}",
        )
        reached = {name for page in pages for name in page}
        self.assertEqual(
            reached, self.mine,
            "the run never even READ some workers - an offset cursor advancing over a "
            "filter the loop mutates walks straight past the rows that shifted down",
        )
        unlinked = sorted(
            w for w in self.mine
            if frappe.db.get_value("Temporary Worker", w, "status") != "Linked"
        )
        self.assertEqual(
            unlinked, [],
            f"workers left unlinked after one full run: {unlinked}",
        )
