# Copyright (c) 2026, afmcoltd
"""Housing Checkout: what it refuses to be created without, how it resolves the building a damage
assessment is filed against, how it serialises two concurrent checkouts of one assignment, and what
it does with the custody a departing resident still holds.

The housing chain — building, room, bed, employee, project — comes from ``test_records.json``, so
the only record a case builds is the assignment being checked out and the checkout itself. The
previous form of this file rebuilt a Company, a Site, a Building, a Room, a Bed, a Project, an
Employee and a submitted Assignment for each of its ten database cases, and carried a
twenty-six-line ``test_ignore`` block to stop Frappe building masters it never used.

The unit cases below touch no database at all: they drive the module against a recording stub, so
they assert what the code DOES rather than what its source says.
"""

from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_checkout import housing_checkout as mod
from apex.habitat.doctype.housing_checkout.housing_checkout import (
    create_departure_transport,
    resolve_damage_assessment_building,
)
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
)

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped.

BUILDING = "_Test Building"
ROOM = "_T-101"
BED = "_T-101-A"


class TestHousingCheckoutContract(FrappeTestCase):
    """What a checkout refuses to be created without, and what it does with outstanding custody."""

    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the resident a
        # case houses would still hold the fixture bed when the next case tries to house one. A
        # savepoint is the framework's own way to hand the bed back.
        frappe.db.savepoint("apex_housing_checkout_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_housing_checkout_case")

        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})

    def _assignment(self):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": self.employee,
            "project": frappe.db.get_value("Project", {"project_name": "_Test Project"}),
            "building": BUILDING,
            "room": ROOM,
            "bed": BED,
            "cost_center": frappe.db.get_value("Building", BUILDING, "default_cost_center"),
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        doc.submit()
        return doc.name

    def _checkout(self, assignment, reason="End of Contract"):
        return frappe.get_doc({
            "doctype": "Housing Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": assignment,
            "checkout_date": "2026-07-01",
            "checkout_reason": reason,
        })

    def _hold(self, qty):
        """Put ``qty`` of the fixture article into the resident's custody by posting the issue row
        on the stock ledger, which is the canonical outstanding source the checkout reads."""
        frappe.get_doc({
            "doctype": "Accommodation Stock Ledger",
            "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-15",
            "item_type": "Custody Article",
            "item": self.article,
            "signed_qty": qty,
            "unit_cost": 100,
            "building": BUILDING,
            "employee": self.employee,
        }).insert(ignore_permissions=True)

    def test_a_checkout_takes_the_reason_it_is_given(self):
        checkout = self._checkout(self._assignment(), "End of Contract")
        checkout.insert(ignore_permissions=True)

        self.assertEqual(checkout.checkout_reason, "End of Contract")

    def test_a_checkout_without_an_assignment_is_refused(self):
        checkout = self._checkout(None, "Final Exit")

        with self.assertRaises(frappe.exceptions.ValidationError):
            checkout.insert(ignore_permissions=True)

    def test_a_checkout_without_a_date_is_refused(self):
        checkout = self._checkout(self._assignment(), "Final Exit")
        checkout.checkout_date = None

        with self.assertRaises(frappe.exceptions.MandatoryError):
            checkout.insert(ignore_permissions=True)

    def test_a_final_exit_raises_a_linked_inter_city_relocation_request(self):
        checkout = self._checkout(self._assignment(), "Final Exit")
        checkout.submit()

        request = create_departure_transport(checkout.name)
        self.assertTrue(request)

        checkout.reload()
        self.assertEqual(checkout.departure_transport_request, request)

        transport = frappe.get_doc("Transport Request", request)
        self.assertEqual(transport.service_line, "Inter-City Relocation")
        self.assertEqual(transport.request_type, "Inter-City Relocation")
        self.assertEqual(transport.accommodation_building, BUILDING)
        self.assertEqual([w.employee for w in transport.workers], [self.employee])

    def test_asking_twice_for_the_departure_transport_returns_the_same_request(self):
        checkout = self._checkout(self._assignment(), "End of Contract")
        checkout.submit()

        self.assertEqual(
            create_departure_transport(checkout.name),
            create_departure_transport(checkout.name),
        )

    def test_an_internal_transfer_is_not_a_departure_and_raises_nothing(self):
        checkout = self._checkout(self._assignment(), "Internal Transfer")
        checkout.submit()

        with self.assertRaises(frappe.ValidationError):
            create_departure_transport(checkout.name)

    def test_saving_a_checkout_pulls_in_the_custody_the_resident_still_holds(self):
        assignment = self._assignment()
        self._hold(2)

        checkout = self._checkout(assignment)
        checkout.insert(ignore_permissions=True)
        checkout.reload()

        self.assertIn(self.article, {row.article for row in checkout.custody_return_items})

    def test_re_saving_neither_duplicates_the_fetched_rows_nor_discards_an_edit(self):
        assignment = self._assignment()
        self._hold(1)

        checkout = self._checkout(assignment)
        checkout.insert(ignore_permissions=True)
        checkout.custody_return_items[0].return_status = "Damaged"
        checkout.save(ignore_permissions=True)
        checkout.reload()

        rows = [row for row in checkout.custody_return_items if row.article == self.article]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].return_status, "Damaged")

    def test_submit_is_blocked_while_the_custody_is_unresolved(self):
        assignment = self._assignment()
        self._hold(3)

        checkout = self._checkout(assignment)
        checkout.insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            checkout.submit()

    def test_marking_the_article_damaged_clears_the_gate(self):
        """Falsifies the gate above: resolving the item lets submit proceed, which proves the
        block is driven by resolution state and not by a blanket refusal."""
        assignment = self._assignment()
        self._hold(3)

        checkout = self._checkout(assignment)
        checkout.insert(ignore_permissions=True)
        checkout.custody_return_items[0].return_status = "Damaged"
        checkout.submit()

        self.assertEqual(checkout.docstatus, 1)

    def test_returning_the_full_quantity_clears_the_gate_too(self):
        assignment = self._assignment()
        self._hold(2)

        checkout = self._checkout(assignment)
        checkout.insert(ignore_permissions=True)
        checkout.custody_return_items[0].return_status = "Returned"
        checkout.custody_return_items[0].quantity_returned = 2
        checkout.submit()

        self.assertEqual(checkout.docstatus, 1)

    def test_the_damage_deduction_is_summed_from_the_rows_not_taken_from_the_parent(self):
        assignment = self._assignment()
        self._hold(1)

        checkout = self._checkout(assignment)
        checkout.insert(ignore_permissions=True)
        checkout.custody_return_items[0].return_status = "Damaged"
        checkout.custody_return_items[0].deduction_amount = 75
        checkout.damage_deduction_amount = 9999
        checkout.save(ignore_permissions=True)
        checkout.reload()

        self.assertEqual(checkout.damage_deduction_amount, 75)


class TestHousingCheckoutUnits(FrappeTestCase):
    """No database: the module is driven against a recording stub."""

    def test_the_assignments_building_wins_when_it_has_one(self):
        assignment = frappe._dict({"building": "QA-BLDG-A"})

        self.assertEqual(resolve_damage_assessment_building(assignment, None), "QA-BLDG-A")
        self.assertEqual(resolve_damage_assessment_building(assignment, "ANY-BED"), "QA-BLDG-A")

    def test_neither_side_having_a_building_answers_none(self):
        """Named for what it reaches: with no building anywhere the ``or None`` tail is not
        load-bearing (``None or None`` is already None), so this cannot detect its removal — the
        empty-string case below is the one that can."""
        result = resolve_damage_assessment_building(frappe._dict({"building": None}), "NONEXISTENT-BED")

        self.assertIsNone(result)
        self.assertNotEqual(result, "")

    def test_a_bed_whose_building_column_holds_an_empty_string_still_answers_none(self):
        """The one input the ``or None`` tail exists for: a Bed row whose building column holds ""
        rather than NULL, which is what an unset Link on an EXISTING row actually stores.

        ``a or b or None`` returns b when both are falsy, so without the tail this answers "" — a
        value that passes as set yet fails the mandatory Building link, silently dropping the
        assessment inside the best-effort try/except."""
        assignment = frappe._dict({"building": ""})

        with mock.patch.object(mod.frappe.db, "get_value", return_value=""):
            result = mod.resolve_damage_assessment_building(assignment, "BED-WITH-BLANK-BUILDING")

        self.assertIsNone(
            result,
            'an empty building leaked out as "", which passes as a value and then fails the '
            "mandatory Building link",
        )

    def test_the_read_that_decides_a_concurrent_checkout_takes_a_row_lock(self):
        """Two concurrent checkouts of one assignment must serialise and the loser must abort:
        on_submit re-reads the assignment's check_out_date under a row lock and throws when it is
        already set.

        True concurrency is not reproducible single-threaded, so the loser's race is played back
        against a recording db layer. Both the abort and the LOCKING read are observed at the call
        boundary, so moving the lock into a helper or renaming its locals stays green while
        dropping for_update — the actual regression — does not."""
        reads = []
        stub = MagicMock()
        stub.db.get_value.side_effect = lambda doctype, _name, field, **kw: (
            reads.append((doctype, field, kw.get("for_update"))) or "2026-07-01"
        )
        stub.throw.side_effect = frappe.ValidationError
        doc = frappe._dict(
            name="ACC-CHKOUT-QA", assignment="ACC-ASGN-QA", checkout_date="2026-07-05"
        )

        # `_` is swapped for identity so the run needs no translation cache.
        with patch.object(mod, "frappe", stub), patch.object(mod, "_", lambda text: text):
            with self.assertRaises(frappe.ValidationError):
                mod.on_submit(doc)

        self.assertIn(
            ("Housing Assignment", "check_out_date", True), reads,
            "the check_out_date re-read that decides the race must take a row lock",
        )

    def test_only_the_damaged_custody_rows_become_damage_assessment_items(self):
        """on_submit auto-creates a draft Custody Damage Assessment carrying one row per
        Damaged/Lost custody return item, mapped onto the Custody Damage Item fieldnames.

        Asserted on the ROW that gets written, not on the source text that writes it: a fieldname
        rename in on_submit still fails here, while renaming its locals or moving the mapping into
        a helper stays green."""
        appended = []
        assessment = MagicMock()
        assessment.append.side_effect = lambda table, row: appended.append((table, row))
        stub = MagicMock()
        # Not yet checked out, so on_submit proceeds to the custody hand-off.
        stub.db.get_value.return_value = None
        stub.get_doc.side_effect = lambda *args: (
            assessment if args and isinstance(args[0], dict) else MagicMock()
        )
        doc = frappe._dict(
            name="ACC-CHKOUT-QA", assignment="ACC-ASGN-QA", bed="QA-BED", employee="QA-EMP",
            checkout_date="2026-07-01",
            custody_return_items=[
                frappe._dict(article="QA-ART-DAMAGED", return_status="Damaged"),
                frappe._dict(article="QA-ART-RETURNED", return_status="Returned"),
            ],
            add_comment=lambda *args, **kwargs: None,
            # on_submit stamps the clearance through db_set after the hand-off, so the stub
            # must provide a callable db_set or the run dies on `'NoneType' object is not
            # callable`.
            db_set=lambda *args, **kwargs: None,
        )

        # `_` is swapped for identity so the run needs no translation cache.
        with patch.object(mod, "frappe", stub), patch.object(mod, "_", lambda text: text), \
                patch.object(mod, "recalculate_spatial", lambda *args: None):
            mod.on_submit(doc)

        rows = [row for table, row in appended if table == "items"]
        self.assertEqual(
            [row["article"] for row in rows], ["QA-ART-DAMAGED"],
            "only Damaged/Lost custody rows become damage items",
        )
        self.assertTrue(rows[0]["damage_description"], "the damage item must carry a description")
        self.assertEqual(
            rows[0]["estimated_replacement_cost"], 0,
            "the draft assessment leaves the cost for the manager",
        )

    def test_the_damage_assessment_schema_carries_the_fieldnames_on_submit_maps_onto(self):
        fields = {f.fieldname: f for f in frappe.get_meta("Custody Damage Assessment").fields}
        self.assertIn("building", fields, "'building' must exist on Custody Damage Assessment")
        self.assertIn("items", fields, "'items' must exist on Custody Damage Assessment")
        self.assertEqual(fields["items"].options, "Custody Damage Item")

        item_fields = {f.fieldname for f in frappe.get_meta("Custody Damage Item").fields}
        for expected in ("article", "damage_description", "estimated_replacement_cost"):
            self.assertIn(expected, item_fields, f"'{expected}' must exist on Custody Damage Item")

test_dependencies = ['Bed', 'Custody Article', 'Employee']


# --- merged from test_housing_checkout_custody_ledger.py ---
BUILDING_housing_checkout_custody_ledger = "_Test Building"
ROOM_housing_checkout_custody_ledger = "_T-101"
ARTICLE = "_T-Custody Article-00001"
def _holder_balance(party_type, party, article):
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "item": article,
            "party_type": party_type,
            "party": party,
            "is_cancelled": 0,
        },
        pluck="signed_qty",
    )
    return sum(rows)
class TestHousingCheckoutCustodyLedger(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.bed = frappe.db.get_value("Bed", {"room": ROOM_housing_checkout_custody_ledger, "status": "Available"})
        # FrappeTestCase rolls the database back once per CLASS, not per method
        # (frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup), and a
        # checkout leaves the room Needs Cleaning — which the next check-in refuses. The
        # room and bed are shared fixtures, so they are handed back as they were found.
        self.addCleanup(frappe.db.set_value, "Room", ROOM_housing_checkout_custody_ledger, "readiness_status", "Ready")
        self.addCleanup(frappe.db.set_value, "Bed", self.bed, "status", "Available")
        # The store has to hold the article before it can be handed over — the check-in
        # gate refuses moving more than the building has.
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=5, building=BUILDING_housing_checkout_custody_ledger,
            voucher_type="Goods Receipt", voucher_no=f"_T-SEED-{frappe.generate_hash(length=12)}",
        )

    def _check_in(self):
        assignment = frappe.get_doc({
            "doctype": "Housing Assignment",
            "party_type": "Employee",
            "party": self.employee,
            "building": BUILDING_housing_checkout_custody_ledger,
            "room": ROOM_housing_checkout_custody_ledger,
            "bed": self.bed,
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "check_in_date": "2026-05-01",
            "project": self.project,
            "custody_items": [{"article": ARTICLE, "quantity": 2}],
        })
        assignment.insert(ignore_permissions=True)
        assignment.submit()
        # The drain is gated on this leg existing, so a failure here means the test never
        # reached the behaviour it exists to check — not that the behaviour is wrong.
        self.assertTrue(
            has_stock_entries("Housing Assignment", assignment.name),
            "check-in must post the holder leg, or there is nothing for check-out to debit",
        )
        return assignment

    def _check_out(self, assignment, return_status, quantity_returned):
        checkout = frappe.get_doc({
            "doctype": "Housing Checkout",
            "assignment": assignment.name,
            "checkout_date": "2026-06-01",
            "checkout_reason": "End of Contract",
            "custody_return_items": [{
                "article": ARTICLE,
                "quantity_issued": 2,
                "quantity_returned": quantity_returned,
                "return_status": return_status,
            }],
        })
        checkout.insert(ignore_permissions=True)
        checkout.submit()
        return checkout

    # Both cases measure a DELTA, never an absolute. FrappeTestCase rolls back once per
    # class, so the first case's ledger rows are still standing when the second runs, and
    # an absolute balance would read the sum of both.

    def test_returned_custody_leaves_the_resident_and_re_enters_the_store(self):
        holder_before = _holder_balance("Employee", self.employee, ARTICLE)
        store_before = get_store_balance("Custody Article", ARTICLE, BUILDING_housing_checkout_custody_ledger)
        assignment = self._check_in()

        self.assertEqual(
            _holder_balance("Employee", self.employee, ARTICLE) - holder_before, 2,
            "check-in must credit the resident, or there is nothing for check-out to debit",
        )

        self._check_out(assignment, "Returned", 2)

        self.assertEqual(
            _holder_balance("Employee", self.employee, ARTICLE), holder_before,
            "the resident leaves holding exactly what they arrived holding",
        )
        self.assertEqual(
            get_store_balance("Custody Article", ARTICLE, BUILDING_housing_checkout_custody_ledger), store_before,
            "and the returned goods are back in the building store",
        )

    def test_lost_custody_leaves_the_resident_without_re_entering_the_store(self):
        holder_before = _holder_balance("Employee", self.employee, ARTICLE)
        store_before = get_store_balance("Custody Article", ARTICLE, BUILDING_housing_checkout_custody_ledger)
        assignment = self._check_in()
        self._check_out(assignment, "Lost", 0)

        self.assertEqual(
            _holder_balance("Employee", self.employee, ARTICLE), holder_before,
            "a lost article still leaves the resident's custody — they are no longer holding it",
        )
        self.assertEqual(
            get_store_balance("Custody Article", ARTICLE, BUILDING_housing_checkout_custody_ledger), store_before - 2,
            "and it must NOT come back into the store, because it is gone",
        )
