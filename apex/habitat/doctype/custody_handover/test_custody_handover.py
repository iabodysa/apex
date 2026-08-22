# Copyright (c) 2026, afmcoltd
"""The procurement-to-handover chain: a Goods Receipt books stock into the intake store, a Custody
Handover ships it out under a one-time code, and only the receiving side — never the shipper, never
a wrong code — can confirm the receive leg into the destination store.

The two buildings and the article come from ``test_records.json``; the second fixture building
already carries ``is_procurement_store``, which is what the intake leg needs. The two users are
still built here, because who may confirm and who may not IS the separation of duties under test.
Fixtures replace building a Company, a Site, two Buildings, a Custody Asset Category and a Custody
Article in ``setUp`` per test method, and remove the need for a ``tearDownModule`` that
force-deletes every building on the site to clean up after itself.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from apex.habitat.api.custody_handover import approve_handover, confirm_handover
from apex.tests.factories import make_goods_receipt
import json
from pathlib import Path
from frappe.utils import add_to_date, now_datetime
import apex
from apex.tests.factories import ApexHabitatTestCase

INTAKE = "_Test Building 2"
DESTINATION = "_Test Building"

class TestCustodyHandover(FrappeTestCase):
    def setUp(self):
        frappe.db.savepoint("apex_custody_handover_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_custody_handover_case")
        self.addCleanup(frappe.clear_document_cache, "Habitat Settings", "Habitat Settings")

        frappe.db.set_single_value("Habitat Settings", "require_handover_otp", 1)
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.shipper = self._user("Accommodation Manager")
        self.receiver = self._user("Accommodation Manager")

    def _user(self, *roles):
        email = "ach-{0}@example.com".format(frappe.generate_hash(length=12).lower())
        user = frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "Handover", "send_welcome_email": 0,
        })
        user.insert(ignore_permissions=True)
        user.add_roles(*roles)
        return email

    def _store_balance(self, building):
        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={
                "item_type": "Custody Article", "item": self.article, "building": building,
                "employee": ["is", "not set"], "is_cancelled": 0,
            },
            fields=["signed_qty"],
        )
        return flt(sum(flt(r.signed_qty) for r in rows))

    def _handover(self, qty=5):
        doc = frappe.get_doc({
            "doctype": "Custody Handover",
            "naming_series": "ACC-HND-.YYYY.-.#####",
            "handover_date": today(),
            "from_building": INTAKE,
            "to_building": DESTINATION,
            "procurement_supervisor": self.shipper,
            "receiving_supervisor": self.receiver,
        })
        doc.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def test_the_chain_runs_from_receipt_to_a_code_confirmed_handover(self):
        make_goods_receipt(INTAKE, self.article, self.shipper, 5)
        self.assertEqual(self._store_balance(INTAKE), 5.0)

        handover = self._handover(5)
        code = frappe.response.get("handover_otp")
        self.assertTrue(code and len(code) == 6, "submit must surface a 6-digit code once")

        handover.reload()
        self.assertEqual(handover.status, "Pending Receipt")
        self.assertTrue(handover.otp_hash, "only the hash of the code is persisted")
        self.assertEqual(self._store_balance(INTAKE), 0.0)
        self.assertEqual(self._store_balance(DESTINATION), 0.0, "nothing lands before confirmation")

        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Under Review")
        frappe.set_user(self.receiver)
        self.addCleanup(frappe.set_user, "Administrator")
        approve_handover(handover.name)
        handover.reload()
        self.assertEqual(handover.status, "Approved")
        confirm_handover(handover.name, code)
        frappe.set_user("Administrator")

        handover.reload()
        self.assertEqual(handover.status, "Confirmed")
        self.assertTrue(handover.otp_verified_on)
        self.assertFalse(handover.otp_hash, "the hash is cleared once confirmed")
        self.assertEqual(self._store_balance(DESTINATION), 5.0)
        self.assertEqual(self._store_balance(INTAKE), 0.0)

    def test_the_shipper_may_not_confirm_his_own_handover(self):
        make_goods_receipt(INTAKE, self.article, self.shipper, 3)
        handover = self._handover(3)
        code = frappe.response.get("handover_otp")
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")

        frappe.set_user(self.shipper)
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.PermissionError):
            confirm_handover(handover.name, code)
        frappe.set_user("Administrator")

        handover.reload()
        self.assertEqual(handover.status, "Approved")
        self.assertEqual(self._store_balance(DESTINATION), 0.0)

    def test_a_wrong_code_posts_no_receive_leg_and_counts_the_attempt(self):
        make_goods_receipt(INTAKE, self.article, self.shipper, 2)
        handover = self._handover(2)
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")

        frappe.set_user(self.receiver)
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.ValidationError):
            confirm_handover(handover.name, "000000")
        frappe.set_user("Administrator")

        handover.reload()
        self.assertNotEqual(handover.status, "Confirmed")
        self.assertTrue(handover.otp_hash, "a miss leaves the code live, it does not consume it")
        self.assertEqual(self._store_balance(DESTINATION), 0.0)

test_dependencies = ['Building', 'Custody Article']

_HANDOVER_JSON = Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "custody_handover" / "custody_handover.json"
_DELIVERY_JSON = (
    Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "facility_asset_delivery" / "facility_asset_delivery.json"
)
OTP_LEVEL_ONE_FIELDS = {"otp_hash", "otp_expires_at", "otp_attempts", "otp_locked_until"}
LEVEL_ONE_ROLES = {"System Manager", "Procurement Supervisor", "Accommodation Manager"}
BLIND_ROLE = "Resident Supervisor"
SIGHTED_ROLE = "Procurement Supervisor"
STORED_ATTEMPTS = 2
def _h(n=12):
    return frappe.generate_hash(length=n).upper()
class TestCustodyHandoverOtpPermlevel(ApexHabitatTestCase):
    """Site-bound. Both handover DocTypes share one OTP mechanism — `generate_otp` and
    `hash_otp` live in custody_handover.py and facility_asset_delivery's API imports them —
    so the schema half of this proof covers both shipped files from the mechanism's home."""

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Co",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        cc = frappe.db.get_value(
            "Cost Center", {"is_group": 0, "company": self.company}
        ) or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc({"doctype": "Site", "site_name": _h()}).insert(
            ignore_permissions=True
        )
        self.intake = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Intake " + _h(),
                "site": site.name,
                "total_capacity": 4,
                "company": self.company,
                "default_cost_center": cc,
                "is_procurement_store": 1,
            }
        ).insert(ignore_permissions=True).name
        self.dest = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Dest " + _h(),
                "site": site.name,
                "total_capacity": 4,
                "company": self.company,
                "default_cost_center": cc,
            }
        ).insert(ignore_permissions=True).name
        category = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc(
            {"doctype": "Custody Asset Category", "category_name": "Cat " + _h()}
        ).insert(ignore_permissions=True).name
        self.article = frappe.get_doc(
            {
                "doctype": "Custody Article",
                "naming_series": "ART-.####",
                "article_name": "Item " + _h(),
                "category": category,
                "unit_of_measure": "Nos",
            }
        ).insert(ignore_permissions=True).name

        self.blind = self._scoped_user(BLIND_ROLE)
        self.sighted = self._scoped_user(SIGHTED_ROLE)

    def _scoped_user(self, role):
        """A fresh System User holding exactly one apex role, scoped to the destination
        building.

        Exactly one role, or a fixture that had picked up a second would reach level 1 by
        the back door and the blind half of the pair would prove nothing. The Building User
        Permission is not optional: neither of these roles is in HOUSING_UNSCOPED_ROLES
        (habitat/permissions.py:95), so `dual_building_scoped_has_permission` denies an
        unscoped user at `check_permission` — BEFORE the field strip — and the read would
        fail for the wrong reason.
        """
        email = f"s007-{frappe.generate_hash(length=12).lower()}@example.com"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": role.split()[0],
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": email,
                "allow": "Building",
                "for_value": self.dest,
            }
        ).insert(ignore_permissions=True)
        return email

    def _handover_with_lockout_state(self):
        """A draft handover carrying a distinguishable lockout state.

        Left in draft on purpose: submitting would post the ship leg and issue a real OTP,
        and this proof is about who can SEE the counters, not about the ledger. The values
        are written with `db_set`, which is also how production writes them.
        """
        doc = frappe.get_doc(
            {
                "doctype": "Custody Handover",
                "naming_series": "ACC-HND-.YYYY.-.#####",
                "handover_date": "2026-05-02",
                "from_building": self.intake,
                "to_building": self.dest,
                "procurement_supervisor": self.sighted,
                "receiving_supervisor": self.blind,
            }
        )
        doc.append("items", {"item_type": "Custody Article", "item": self.article, "qty": 2})
        doc.insert(ignore_permissions=True)
        doc.db_set(
            {
                "otp_hash": "f" * 64,
                "otp_attempts": STORED_ATTEMPTS,
                "otp_expires_at": add_to_date(now_datetime(), minutes=10),
                "otp_locked_until": add_to_date(now_datetime(), minutes=5),
            }
        )
        return doc

    def test_the_lockout_state_is_hidden_from_the_blind_role_and_visible_to_the_sighted(self):
        """THE PAIR, in one method so a regression that concealed the counters from BOTH
        roles cannot satisfy the blind half and look correct."""
        doc = self._handover_with_lockout_state()

        frappe.set_user(self.blind)
        concealed = frappe.client.get("Custody Handover", doc.name)
        self.assertNotEqual(
            frappe.utils.cint(concealed.get("otp_attempts")),
            STORED_ATTEMPTS,
            f"{BLIND_ROLE} can still read otp_attempts — the guesser's feedback channel is "
            "open",
        )
        self.assertIsNone(
            concealed.get("otp_locked_until"), f"{BLIND_ROLE} can still read otp_locked_until"
        )
        self.assertIsNone(
            concealed.get("otp_expires_at"), f"{BLIND_ROLE} can still read otp_expires_at"
        )
        self.assertIsNone(
            concealed.get("otp_hash"),
            "precondition: the pre-existing level-1 hash must also be concealed",
        )
        self.assertEqual(
            concealed.get("status"),
            doc.status,
            "level-0 fields must survive the strip — the role still runs the handover",
        )

        frappe.set_user(self.sighted)
        visible = frappe.client.get("Custody Handover", doc.name)
        self.assertEqual(
            frappe.utils.cint(visible.get("otp_attempts")),
            STORED_ATTEMPTS,
            f"{SIGHTED_ROLE} lost the attempt counter it is supposed to hold",
        )
        self.assertTrue(
            visible.get("otp_locked_until"), f"{SIGHTED_ROLE} lost the lockout stamp"
        )
        self.assertTrue(
            visible.get("otp_expires_at"), f"{SIGHTED_ROLE} lost the expiry window"
        )

    def test_the_blind_role_can_still_save_without_wiping_the_lockout(self):
        """The regression this move could plausibly have caused.

        The receiving side keeps level-0 write. A Desk save by that role now arrives with
        the four fields STRIPPED, and `reset_values_if_no_permlevel_access` restores them
        from `get_latest()` — the stored row (base_document.py:1288). If it blanked them
        instead, an ordinary save by the receiving supervisor would clear a live lockout,
        which is a wider hole than the one this card closed.
        """
        doc = self._handover_with_lockout_state()

        frappe.set_user(self.blind)
        editing = frappe.get_doc("Custody Handover", doc.name)
        editing.apply_fieldlevel_read_permissions()
        self.assertIsNone(
            editing.get("otp_locked_until"),
            "precondition: the read strip must have removed the lockout for this role",
        )
        editing.all_items_verified = 1
        editing.save()

        stored = frappe.db.get_value(
            "Custody Handover",
            doc.name,
            ["otp_attempts", "otp_locked_until", "otp_hash"],
            as_dict=True,
        )
        self.assertEqual(
            stored.otp_attempts,
            STORED_ATTEMPTS,
            "a save by the role that cannot see the counter reset it — the lockout is "
            "clearable by anyone who can press Save",
        )
        self.assertTrue(stored.otp_locked_until, "the save wiped a live lockout")
        self.assertEqual(stored.otp_hash, "f" * 64, "the save wiped the stored hash")

    def test_both_shipped_handovers_hold_the_whole_otp_block_at_level_one(self):
        """The schema half, over both files. Split levels are the defect itself, so the
        assertion is on the SET: a field left behind at level 0 fails here."""
        for label, path in (
            ("custody_handover", _HANDOVER_JSON),
            ("facility_asset_delivery", _DELIVERY_JSON),
        ):
            with self.subTest(doctype=label):
                shipped = json.loads(path.read_text(encoding="utf-8"))
                otp_fields = {
                    f["fieldname"]: int(f.get("permlevel") or 0)
                    for f in shipped["fields"]
                    if f["fieldname"].startswith("otp_")
                }
                self.assertTrue(otp_fields, f"{label}: no otp_* fields found — scan broke")
                elevated = {name for name, level in otp_fields.items() if level == 1}
                self.assertEqual(
                    elevated,
                    OTP_LEVEL_ONE_FIELDS,
                    f"{label}: the level-1 OTP field set is not the hash plus its lockout "
                    "state. A counter at level 0 tells an unprivileged reader how many "
                    "guesses are left and when the lock lifts",
                )

    def test_the_move_added_no_permission_row(self):
        """The cost claim, read off both shipped files rather than trusted.

        The level-1 readers already existed, so this change was a field move, not a grant.
        The pair (role, permlevel) is the identity — `is_perm_applicable` keeps only
        level-0 rows (frappe/permissions.py:284) — so these rows coexist with the level-0
        rows for the same roles by design.
        """
        for label, path in (
            ("custody_handover", _HANDOVER_JSON),
            ("facility_asset_delivery", _DELIVERY_JSON),
        ):
            with self.subTest(doctype=label):
                shipped = json.loads(path.read_text(encoding="utf-8"))
                rows = shipped["permissions"]
                high = [p for p in rows if int(p.get("permlevel") or 0) == 1]
                self.assertEqual(
                    {p["role"] for p in high},
                    LEVEL_ONE_ROLES,
                    f"{label}: the level-1 role set changed — the OTP block was moved to an "
                    "EXISTING readership, not to a new one",
                )
                for row in high:
                    self.assertEqual(
                        row.get("read"), 1, f"{label}/{row['role']}: level-1 read missing"
                    )
                    self.assertNotEqual(
                        row.get("write"),
                        1,
                        f"{label}/{row['role']}: gained level-1 write. Nothing needs it — "
                        "every OTP write in production goes through db_set, which skips "
                        "permlevel entirely",
                    )
                blind = [
                    p
                    for p in rows
                    if p["role"] == BLIND_ROLE and int(p.get("permlevel") or 0) == 0
                ]
                self.assertEqual(len(blind), 1, f"{label}: {BLIND_ROLE} row went missing")
                self.assertEqual(
                    blind[0].get("write"),
                    1,
                    f"{label}: {BLIND_ROLE}'s level-0 write was collateral damage",
                )
                self.assertNotIn(
                    BLIND_ROLE,
                    {p["role"] for p in high},
                    f"{label}: {BLIND_ROLE} gained level-1 access",
                )
