# Copyright (c) 2026, afmcoltd
"""What a Subcontractor Service Order guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_update_after_submit``) for the status-transition guarantees, and
``test_validate`` for the pricing/defaulting behaviour in ``before_save`` (a module-level
function wired through ``hooks.py``'s ``doc_events``, so it only runs through the real
``insert()``/``save()`` call). There is no ``test_records.json`` for this DocType, so
every subject here is built with ``frappe.new_doc`` inside its own test method, with every
field verified against ``subcontractor_service_order.json`` first.

Four guarantees: ``before_save`` prices the order from its line items when any exist
(and otherwise leaves Finance's typed ``service_cost`` alone — the permlevel-1 field
overlay this controller exists to protect) and computes VAT from whichever base results;
it stamps who confirmed the visit and clears that stamp the moment the tick is cleared;
and ``start_work`` / ``mark_completed`` / ``mark_missed`` gate the order's status through
one chokepoint each rather than a free-form edit.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order import (
    mark_completed,
    mark_missed,
    start_work,
)

test_dependencies = ["Building", "Subcontractor Service Contract"]


def _new_contract():
    contract = frappe.copy_doc(
        frappe.get_test_records("Subcontractor Service Contract")[0]
    )
    contract.insert()
    return contract.name


def _new_order(scheduled_date, contract, **fields):
    order = frappe.new_doc("Subcontractor Service Order")
    order.building = "_Test Building"
    order.contract = contract
    order.scheduled_date = scheduled_date
    for fieldname, value in fields.items():
        order.set(fieldname, value)
    return order


class TestSubcontractorServiceOrder(FrappeTestCase):
    def test_lines_recompute_the_service_cost_and_its_vat(self):
        """The moment a line exists, the total is arithmetic — a hand-typed
        service_cost gives way to the sum of the lines."""
        order = _new_order("2026-01-06", _new_contract(), service_cost=999, tax_rate=15)
        order.append(
            "service_items", {"description": "_Test Pump Service", "qty": 2, "rate": 100}
        )

        order.insert()

        self.assertEqual(order.service_cost, 200)
        self.assertEqual(order.tax_amount, 30)
        self.assertEqual(order.grand_total, 230)

    def test_an_order_with_no_lines_keeps_its_typed_service_cost(self):
        """A flat call-off against the contract rate has no lines to derive a cost from —
        the field overlay Finance Manager holds must not be overwritten out from under
        it."""
        order = _new_order("2026-01-07", _new_contract(), service_cost=300, tax_rate=15)

        order.insert()

        self.assertEqual(order.service_cost, 300)
        self.assertEqual(order.tax_amount, 45)
        self.assertEqual(order.grand_total, 345)

    def test_confirming_a_visit_stamps_who_and_when_and_unconfirming_clears_it(self):
        """A bare checkbox names nobody; the stamp must bind to a person and disappear the
        moment the confirmation is withdrawn."""
        order = _new_order("2026-01-08", _new_contract(), supervisor_confirmed=1)
        order.insert()

        self.assertEqual(order.confirmed_by, frappe.session.user)
        self.assertTrue(order.confirmed_on)

        order.supervisor_confirmed = 0
        order.save()

        self.assertFalse(order.confirmed_by)
        self.assertFalse(order.confirmed_on)

    def test_start_work_moves_a_scheduled_order_to_in_progress(self):
        """The one legitimate way a supervisor signals the visit has begun."""
        order = _new_order("2026-01-09", _new_contract())
        order.insert()
        order.submit()

        result = start_work(order.name)

        self.assertEqual(result["status"], "In Progress")
        self.assertEqual(
            frappe.db.get_value("Subcontractor Service Order", order.name, "status"),
            "In Progress",
        )

    def test_start_work_refuses_an_order_that_is_not_scheduled(self):
        """Starting an already-started order a second time would silently re-stamp its
        comment trail rather than surface the double-trigger."""
        order = _new_order("2026-01-10", _new_contract())
        order.insert()
        order.submit()
        start_work(order.name)

        with self.assertRaisesRegex(frappe.ValidationError, "status Scheduled"):
            start_work(order.name)

    def test_mark_completed_records_the_visit_evidence_and_completes(self):
        """Completion is the one door through which visit evidence — the confirmation,
        the notes, the actual visit date — is recorded together with the status."""
        order = _new_order("2026-01-11", _new_contract())
        order.insert()
        order.submit()
        start_work(order.name)

        result = mark_completed(
            order.name, visit_notes="_Test all fixtures replaced", supervisor_confirmed=1
        )

        self.assertEqual(result["status"], "Completed")
        row = frappe.db.get_value(
            "Subcontractor Service Order",
            order.name,
            ["status", "visit_notes", "supervisor_confirmed"],
            as_dict=True,
        )
        self.assertEqual(row.status, "Completed")
        self.assertEqual(row.visit_notes, "_Test all fixtures replaced")
        self.assertEqual(row.supervisor_confirmed, 1)

    def test_mark_completed_refuses_an_order_that_is_not_in_progress(self):
        """An order that never started cannot be closed out as finished work."""
        order = _new_order("2026-01-12", _new_contract())
        order.insert()
        order.submit()

        with self.assertRaisesRegex(frappe.ValidationError, "status In Progress"):
            mark_completed(order.name)

    def test_mark_missed_refuses_before_the_scheduled_date(self):
        """A visit cannot be declared missed before the date it was even due."""
        future_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)
        order = _new_order(future_date, _new_contract())
        order.insert()
        order.submit()
        start_work(order.name)

        with self.assertRaisesRegex(frappe.ValidationError, "Cannot mark Missed before"):
            mark_missed(order.name)

    def test_mark_missed_is_accepted_on_or_after_the_scheduled_date(self):
        """The acceptance counterpart to the refusal above — a visit due today or earlier
        can be declared missed."""
        order = _new_order(frappe.utils.nowdate(), _new_contract())
        order.insert()
        order.submit()
        start_work(order.name)

        result = mark_missed(order.name)

        self.assertEqual(result["status"], "Missed")
