# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
# [#gi2kqa]

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

_LEDGER_JSON = Path(__file__).resolve().parent / "accommodation_stock_ledger.json"
_SNAPSHOT_JSON = (
    _LEDGER_JSON.parent.parent / "occupancy_snapshot" / "occupancy_snapshot.json"
)

OVERSIGHT_ROLES = ("Finance Manager", "Internal Auditor")
OVERSIGHT_FLAGS = ("read", "report", "export", "print", "email", "share")


def _rows(path, role):
    """The role's permlevel-0 DocPerm rows off the SHIPPED JSON.

    Keyed on the (role, permlevel) PAIR: a permlevel-1 row is not a duplicate of the
    level-0 one, and matching on role alone would conflate them. The file is read
    rather than ``frappe.get_meta`` so the verdict grades what migrate will import,
    not whatever an un-migrated site still holds.
    """
    perms = json.loads(path.read_text(encoding="utf-8"))["permissions"]
    return [p for p in perms if p["role"] == role and int(p.get("permlevel") or 0) == 0]


class TestTheEstateWideOversightGrantIsDeliberate(FrappeTestCase):
    """The owner decision recorded in this module's controller docstring, made falsifiable.

    The grant lets two oversight roles read per-worker custody holdings with a per-person
    value across every building. It was reviewed and KEPT. This asserts the shape that
    decision was taken against, so changing it forces the written reason to be revisited
    instead of the exposure being re-discovered at the next audit.
    """

    def test_both_oversight_roles_hold_one_matching_level_zero_row(self):
        rows = {}
        for role in OVERSIGHT_ROLES:
            found = _rows(_LEDGER_JSON, role)
            self.assertEqual(
                len(found), 1, f"{role} lost or gained a permlevel-0 row on the ledger"
            )
            rows[role] = found[0]
            for flag in OVERSIGHT_FLAGS:
                self.assertEqual(
                    found[0].get(flag), 1, f"{role} permlevel-0 {flag} changed"
                )
        self.assertEqual(
            {k: v for k, v in rows["Finance Manager"].items() if k != "role"},
            {k: v for k, v in rows["Internal Auditor"].items() if k != "role"},
            "the two oversight rows diverged -- they were kept BECAUSE they matched, so "
            "whichever one moved now needs its own recorded reason",
        )

    def test_the_finance_row_is_matched_on_the_occupancy_snapshot(self):
        """The third of the three grants. One grant is a slip; three across two records
        and two roles is the design the decision rests on."""
        found = _rows(_SNAPSHOT_JSON, "Finance Manager")
        self.assertEqual(len(found), 1, "Finance Manager lost its Occupancy Snapshot row")
        for flag in OVERSIGHT_FLAGS:
            self.assertEqual(found[0].get(flag), 1, f"Occupancy Snapshot {flag} changed")

    def test_neither_role_is_row_scoped_to_a_building(self):
        """Why the grant is ESTATE-wide rather than per-building: both roles sit in
        ``HOUSING_UNSCOPED_ROLES``, so the ledger's query condition adds no filter."""
        from apex.habitat.permissions import HOUSING_UNSCOPED_ROLES

        for role in OVERSIGHT_ROLES:
            self.assertIn(
                role,
                HOUSING_UNSCOPED_ROLES,
                f"{role} became building-scoped -- the recorded reason describes an "
                "estate-wide grant and no longer matches the code",
            )

    def test_the_ledger_still_carries_no_permission_levels(self):
        """The reviewability clause. The decision was taken against an all-or-nothing
        record: with no levels, a level-0 read is EVERY field, custodian and unit cost
        included. The day levels arrive, the grant can be narrowed to the fields finance
        needs without touching either role's scope -- so re-read the decision then.
        """
        data = json.loads(_LEDGER_JSON.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted({int(f.get("permlevel") or 0) for f in data["fields"]}),
            [0],
            "a field level appeared -- narrowing this grant is now possible, which is "
            "exactly the condition the recorded decision said to revisit it under",
        )
        self.assertEqual(
            sorted({int(p.get("permlevel") or 0) for p in data["permissions"]}),
            [0],
            "a permlevel-1 DocPerm row appeared on a record with no level-1 fields",
        )


class TestAccommodationStockLedger(FrappeTestCase):
    def test_insert_minimal_ledger_row(self):
        """Smoke test: a minimal valid Stock Ledger row (all mandatory fields set)
        inserts, gets a name, and deletes cleanly. The item / building Links are
        supplied as placeholders with ignore_links=True so the smoke test exercises
        the row write path without standing up the full master chain."""
        doc = frappe.get_doc({
            "doctype": "Accommodation Stock Ledger",
            "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-01",
            "item_type": "Custody Article",
            "item": "SLE-SMOKE-ITEM",
            "signed_qty": 1,
            "building": "SLE-SMOKE-BLDG",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)

        frappe.delete_doc("Accommodation Stock Ledger", doc.name, force=True, ignore_permissions=True)
