# Copyright (c) 2026, AFMCO and contributors
"""The OTP lockout state now sits at the same level as the hash it protects.

`otp_hash` shipped at permlevel 1 on both handover DocTypes; `otp_expires_at`,
`otp_attempts` and `otp_locked_until` shipped at permlevel 0. Concealing the hash while
publishing the counters is a half-closed door: the counters are the brute-forcer's
feedback channel. `otp_attempts` says how many guesses remain before the lock, so a
guesser can stop at two and never trip it; `otp_locked_until` says exactly when to resume;
`otp_expires_at` says how long the window stays open. Resident Supervisor holds read+write
at level 0 on every handover its building scope reaches and NO level-1 row, so that whole
channel was readable by a role deliberately kept away from the hash.

The three fields moved to permlevel 1. No DocPerm row changed: the level-1 readers were
already System Manager, Procurement Supervisor and Accommodation Manager.

WHY THIS COULD NOT BREAK THE LOCKOUT
------------------------------------
Permlevel is enforced in `validate_higher_perm_levels` on the save path
(frappe/model/document.py:306,412) and in `apply_fieldlevel_read_permissions` on the API
read path (:754). Every read of these counters goes through `frappe.db.get_value`
(habitat/api/custody_handover.py:72, habitat/api/facility_asset_delivery.py) and every
write through `Document.db_set` (custody_handover.py:127, api/custody_handover.py:105,110,
150) — neither touches either enforcement point. The lockout arithmetic is untouched; only
who may SEE it changed.

READING THE CONCEALED VALUES IS NOT `assertIsNone`
--------------------------------------------------
`apply_fieldlevel_read_permissions` deletes the attribute (document.py:771) but
`frappe.client.get` returns `doc.as_dict()` (frappe/client.py:112), which rebuilds every
column and coerces it by fieldtype. A concealed Datetime therefore reads back None while a
concealed Int reads back 0 — so `otp_attempts` is graded against the value that was
actually stored, never against None, which would pass on any Int whatever the level.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.custody_handover.test_custody_handover_otp_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import add_to_date, now_datetime

import apex
from apex.tests.factories import ApexHabitatTestCase

_HANDOVER_JSON = Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "custody_handover" / "custody_handover.json"
_DELIVERY_JSON = (
    Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "facility_asset_delivery" / "facility_asset_delivery.json"
)

# The lockout channel, plus the hash it was already protecting. Asserted as one set below:
# the point of the change is that all four sit at the SAME level.
OTP_LEVEL_ONE_FIELDS = {"otp_hash", "otp_expires_at", "otp_attempts", "otp_locked_until"}

LEVEL_ONE_ROLES = {"System Manager", "Procurement Supervisor", "Accommodation Manager"}
# Level-0 read+write and no level-1 row — the role this change was written for.
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
        # frappe.session.user is process state; no rollback restores it.
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
