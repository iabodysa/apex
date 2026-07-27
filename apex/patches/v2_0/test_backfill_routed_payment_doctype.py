# Copyright (c) 2026, AFMCO and contributors
"""Guard for the routed-payment link backfill.

The patch has to answer one question per historical row -- which table does this
payment name live in -- and its value is entirely in what it does when it CANNOT
answer. A guessed type is indistinguishable from a correct one once written, so an
unresolvable row must stay blank and be reported, never filled in with the most
likely candidate.

Both halves run in the same test: a resolvable row must actually be typed, or
"leaves it blank" would pass on a patch that simply does nothing.

The third test guards the batched lookup: the answer has to stay the same for every
row shape while the number of queries stops following the row count.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.payment_router import (
    LINK_DOCTYPE_FIELD,
    LINK_NAME_FIELD,
    SOURCE_DOCTYPE,
)
from apex.patches.v2_0.backfill_routed_payment_doctype import (
    LEGACY_TARGET_DOCTYPE,
    _candidate_doctypes,
    execute,
)

ROUTER = "Payment Routing Settings"

# Rows per shape (resolvable / ambiguous / no-match). 3 x 20 = 60 untyped rows, past the
# 50 the bound is about, and enough that the pre-change O(rows x candidates) probe would
# have run ~180 queries where the batched one runs at most len(_candidate_doctypes()).
ROWS_PER_SHAPE = 20


class TestBackfillRoutedPaymentDoctype(FrappeTestCase):
    def _untyped_request(self, payment_name):
        """A Salis Payment Request carrying an untyped payment link, exactly the shape
        of a row written before ``linked_payment_doctype`` existed."""
        pr = frappe.get_doc(
            {"doctype": SOURCE_DOCTYPE, "expense_type": "Fuel", "amount": 10, "status": "Draft"}
        )
        pr.insert(ignore_permissions=True)
        frappe.db.set_value(
            SOURCE_DOCTYPE,
            pr.name,
            {LINK_NAME_FIELD: payment_name, LINK_DOCTYPE_FIELD: None},
            update_modified=False,
        )
        return pr.name

    def test_types_a_resolvable_link_and_refuses_to_guess_an_unresolvable_one(self):
        # Note becomes a candidate by being the configured target, which also proves
        # the patch reads the router's config rather than a hard-coded list. Cleanup
        # is registered BEFORE the write: a Single is the one thing rollback is least
        # reliable about, and leaving this set would re-point a later module's router.
        self.addCleanup(frappe.db.set_single_value, ROUTER, "target_payment_doctype", None)
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", "Note")
        note = frappe.get_doc(
            {"doctype": "Note", "title": f"Apex A278 {frappe.generate_hash(length=14)}"}
        ).insert(ignore_permissions=True)

        resolvable = self._untyped_request(note.name)
        orphan = f"APEX-A278-ABSENT-{frappe.generate_hash(length=14)}"
        unresolvable = self._untyped_request(orphan)

        # frappe.db.commit is suppressed so the fixtures stay inside the test's
        # transaction; the commit is not the behaviour under test, the typing is.
        with patch.object(frappe.db, "commit"), patch("frappe.log_error") as logged:
            execute()

        self.assertEqual(
            frappe.db.get_value(SOURCE_DOCTYPE, resolvable, LINK_DOCTYPE_FIELD), "Note"
        )
        # Fail closed: no candidate matched, so the type is left blank ...
        self.assertFalse(frappe.db.get_value(SOURCE_DOCTYPE, unresolvable, LINK_DOCTYPE_FIELD))
        # ... and surfaced, so it is a visible gap rather than a silent one.
        self.assertTrue(logged.called)
        self.assertIn(orphan, logged.call_args.kwargs["message"])

    def test_already_typed_rows_are_left_alone(self):
        """Idempotence: a second migrate must not re-decide a row that already has a
        type, or a hand-corrected row would be overwritten by the guess it replaced."""
        self.addCleanup(frappe.db.set_single_value, ROUTER, "target_payment_doctype", None)
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", "Note")
        note = frappe.get_doc(
            {"doctype": "Note", "title": f"Apex A278 {frappe.generate_hash(length=14)}"}
        ).insert(ignore_permissions=True)
        request = self._untyped_request(note.name)
        frappe.db.set_value(
            SOURCE_DOCTYPE, request, LINK_DOCTYPE_FIELD, "Payment Entry", update_modified=False
        )

        with patch.object(frappe.db, "commit"), patch("frappe.log_error"):
            execute()

        self.assertEqual(
            frappe.db.get_value(SOURCE_DOCTYPE, request, LINK_DOCTYPE_FIELD), "Payment Entry"
        )

    def test_batched_lookup_bounds_the_query_count_and_changes_no_verdict(self):
        """The existence probe is one query per candidate DocType for the whole run, not
        one per (row, candidate) pair -- and every row still gets the answer the per-row
        probe gave it. Both halves are asserted together: the bound alone would pass on a
        patch that stopped looking anything up, and the verdicts alone would pass on the
        version this replaced.
        """
        # The configured target is the one candidate this test puts rows into, and the
        # ambiguity needs a row NAMED exactly after the legacy candidate -- so it has to
        # be a DocType whose docname is settable. Role is ``autoname: field:role_name``
        # (frappe/core/doctype/role/role.json:4). Not Note: Note is ``autoname: hash``
        # (frappe/desk/doctype/note/note.json:3), so a Note titled "Payment Entry" is
        # named a random hash, the second match never existed, and every row this test
        # called ambiguous was really a plain resolvable one.
        configured = "Role"
        self.addCleanup(frappe.db.set_single_value, ROUTER, "target_payment_doctype", None)
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", configured)

        candidates = _candidate_doctypes()
        self.assertLessEqual(len(candidates), 3)
        # The ambiguity below needs the legacy candidate present. It is an ERPNext
        # DocType and ERPNext is a required app, so this is a precondition, not a skip.
        self.assertIn(LEGACY_TARGET_DOCTYPE, candidates)

        # An ambiguous name has to match two candidates at once, without building an
        # ERPNext payment. frappe.db.exists returns the name unread when the DocType
        # equals it (frappe/database/database.py:1259-1261), so the legacy candidate
        # matches this name on its own; a row named after it in the configured candidate
        # supplies the second match.
        ambiguous = LEGACY_TARGET_DOCTYPE
        if not frappe.db.exists(configured, ambiguous):
            frappe.get_doc({"doctype": configured, "role_name": ambiguous}).insert(
                ignore_permissions=True
            )
        # Asserted, never assumed: this row's NAME is the entire ambiguity, and the naming
        # rule behind it is exactly what the first version of this test got wrong.
        self.assertTrue(frappe.db.exists(configured, ambiguous))

        payments = {}
        expected = {}
        for _ in range(ROWS_PER_SHAPE):
            # Read the name back instead of predicting it -- a resolvable row only has to
            # exist in exactly one candidate, whatever it ended up being called.
            resolvable = frappe.get_doc(
                {
                    "doctype": configured,
                    "role_name": f"Apex A278 {frappe.generate_hash(length=14)}",
                }
            ).insert(ignore_permissions=True)
            orphan = f"APEX-A278-ABSENT-{frappe.generate_hash(length=14)}"
            for payment, verdict in (
                (resolvable.name, configured),
                (ambiguous, None),
                (orphan, None),
            ):
                request = self._untyped_request(payment)
                payments[request] = payment
                expected[request] = verdict
        self.assertGreaterEqual(len(payments), 50)

        # The pre-change verdict, recomputed over the same fixture with the exact
        # expression the batching replaced, so "identical to before" is measured rather
        # than recalled. Cross-checked against the hand-written table so an empty
        # candidate list could not make the two agree vacuously.
        per_row_verdict = {}
        for request, payment in payments.items():
            matches = [dt for dt in candidates if frappe.db.exists(dt, payment)]
            per_row_verdict[request] = matches[0] if len(matches) == 1 else None
        self.assertEqual(per_row_verdict, expected)

        # frappe.db.sql is the one choke point every read funnels through -- get_all,
        # db.exists and frappe.qb all end up there (frappe/query_builder/utils.py:87) --
        # so counting the statements naming a candidate's table cannot be dodged by
        # switching which ORM call the patch uses. Values reach that layer as bound
        # parameters, never interpolated, so no payload can spoof a table name into it.
        # The match is a bare substring, so a table merely PREFIXED by a candidate's
        # ("tabRole Profile") would over-count. Deliberate: nothing execute() touches is
        # named that way, and over-counting fails loudly with the statements attached,
        # where matching the closing quote instead would count zero and pass in silence
        # the day the quoting character changes.
        candidate_tables = tuple(f"tab{doctype}" for doctype in candidates)
        probes = []
        real_sql = frappe.db.sql

        def counting_sql(query, *args, **kwargs):
            text = query if isinstance(query, str) else str(query)
            if any(table in text for table in candidate_tables):
                probes.append(text)
            return real_sql(query, *args, **kwargs)

        with (
            patch.object(frappe.db, "sql", counting_sql),
            patch.object(frappe.db, "commit"),
            patch("frappe.log_error") as logged,
        ):
            execute()

        # One lookup per candidate for all 60 rows. The per-row probe ran ~180. The
        # statements are carried into the failure message so an over-count names itself
        # instead of costing a second run to find.
        self.assertLessEqual(len(probes), len(candidates), msg="\n".join(probes))

        self.assertEqual(
            {
                request: frappe.db.get_value(SOURCE_DOCTYPE, request, LINK_DOCTYPE_FIELD) or None
                for request in payments
            },
            per_row_verdict,
        )

        # The match COUNT is what decides a row, so pin it: a batch that lost the
        # short-circuit above would report one match here and type the row instead.
        message = logged.call_args.kwargs["message"]
        self.assertIn(f"{ambiguous} (2 matches)", message)
        self.assertIn("(0 matches)", message)
