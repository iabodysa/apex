# Copyright (c) 2026, afmcoltd
"""get_expected_arrivals — the Intake zone's pre-arrival manifest, and who may read it.

``building`` is an OPTIONAL argument: omitting it must still scope the caller to their own
building, not "the whole estate" — a regression would show a building-scoped supervisor
every building's manifest for the date, each row carrying an expected worker's name,
passport number and nationality. That is cross-tenant PII, not an aggregate — which is why
these cases assert over the ROWS and their passport numbers rather than over a count.

The two registered scope primitives cannot reach this endpoint, so a test that only
proved they are registered would prove nothing. ``frappe.get_all`` hardcodes
``ignore_permissions=True``, so the ``permission_query_conditions`` fragment never runs;
the ``has_permission`` hook is dispatched only from ``get_doc_permissions``, which the
type-level gate — passing no doc — never reaches. The third primitive, the report scope
tuple, is spliced into the filter, and that splice is what is graded here.

The building, its room and bed and the supplier all come from ``test_records.json``.
Batches a case writes are rolled back to a savepoint before the next one runs, so each
manifest is exactly the one its case built.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions
from apex.habitat.api.arrivals_desk import get_expected_arrivals

test_dependencies = ["Bed", "Supplier"]

BUILDING = "_Test Building 2"
OTHER_BUILDING = "_Test Building"
DATE = "2026-06-22"

MINE = "_T Arrival Mine"
THEIRS = "_T Arrival Theirs"
MY_PASSPORT = "PMINE0001"
THEIR_PASSPORT = "PTHEIRS001"


class TestExpectedArrivalsScope(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method, so
        # the batches one case writes would still be on the manifest the next one reads.
        frappe.db.savepoint("apex_expected_arrivals_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_expected_arrivals_case")

        self._batch(BUILDING, MINE, MY_PASSPORT)
        self._batch(OTHER_BUILDING, THEIRS, THEIR_PASSPORT)

    def _batch(self, building, worker_name, passport_number):
        return (
            frappe.get_doc(
                {
                    "doctype": "Arrival Batch",
                    "naming_series": "ARR-BATCH-.YYYY.-.####",
                    "building": building,
                    "expected_date": DATE,
                    "expected_workers": [
                        {"worker_name": worker_name, "passport_number": passport_number}
                    ],
                }
            )
            .insert(ignore_permissions=True, ignore_mandatory=True)
            .name
        )

    def _scope(self, restrict, allowed):
        """Stub the building scope at the resolver the endpoint calls."""
        patcher = patch.object(
            permissions, "report_building_scope", return_value=(restrict, allowed)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _passports(manifest):
        return {w["passport_number"] for w in manifest["workers"]}

    def test_both_buildings_manifests_are_on_the_site(self):
        """The control: without it every assertion below could pass on an empty table."""
        manifest = get_expected_arrivals(date=DATE)

        self.assertEqual({MY_PASSPORT, THEIR_PASSPORT}, self._passports(manifest))
        self.assertEqual(2, manifest["total"])

    def test_omitting_the_building_no_longer_returns_the_whole_estate(self):
        """The defect: no ``building`` meant every building's expected workers."""
        self._scope(True, [BUILDING])
        manifest = get_expected_arrivals(date=DATE)

        self.assertEqual(
            {MY_PASSPORT},
            self._passports(manifest),
            "another building's expected workers were returned to a scoped supervisor",
        )
        self.assertEqual(1, manifest["total"])

    def test_the_leaked_row_carried_passport_and_nationality_not_just_a_count(self):
        """Why this is PII and not telemetry: the row itself crosses the tenant line."""
        self._scope(True, [BUILDING])
        manifest = get_expected_arrivals(date=DATE)

        for worker in manifest["workers"]:
            self.assertIn("passport_number", worker)
            self.assertIn("nationality", worker)
        self.assertNotIn(
            THEIRS,
            [w["worker_name"] for w in manifest["workers"]],
            "an out-of-estate worker's identity reached a scoped supervisor",
        )

    def test_a_supervisor_with_no_building_gets_an_empty_manifest_not_the_estate(self):
        self._scope(True, [])
        manifest = get_expected_arrivals(date=DATE)

        self.assertEqual([], manifest["workers"])
        self.assertEqual(0, manifest["total"])
        self.assertEqual(0, manifest["pending"])

    def test_an_unscoped_reader_still_sees_the_estate(self):
        """The narrowing must not become a wall for the oversight roles it exempts."""
        self._scope(False, [])

        self.assertEqual(
            {MY_PASSPORT, THEIR_PASSPORT}, self._passports(get_expected_arrivals(date=DATE))
        )

    def test_an_explicit_in_scope_building_is_still_answered(self):
        """Scoping must not break the in-scope question it was added to protect."""
        self._scope(True, [BUILDING])
        manifest = get_expected_arrivals(date=DATE, building=BUILDING)

        self.assertEqual({MY_PASSPORT}, self._passports(manifest))
        self.assertEqual(BUILDING, manifest["building"])

    def test_the_scope_is_narrowed_by_the_doctype_the_read_actually_reads(self):
        """A User Permission narrowed by ``applicable_for`` only applies to the DocType it
        names, so the report scope has to be asked for the one this endpoint reads."""
        with patch.object(
            permissions, "report_building_scope", return_value=(True, [BUILDING])
        ) as scope:
            get_expected_arrivals(date=DATE)

        self.assertEqual("Arrival Batch", scope.call_args.kwargs.get("doctype"))
