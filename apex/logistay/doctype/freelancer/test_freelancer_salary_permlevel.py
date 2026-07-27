# Copyright (c) 2026, AFMCO and contributors
"""`monthly_salary` moved to permlevel 1, and what that actually changed.

The field_sensitivity model calls per-person pay a level-1 category: what one named person
is paid belongs beside this record's national ID, not beside its contract dates. Freelancer
already ran a level-1 section for `national_id_or_iqama` and `mobile_number`, and Finance
Manager and System Manager already held the level-1 read+write rows, so this move cost NO
new DocPerm row — `test_the_move_added_no_permission_row` proves that off the shipped JSON
rather than asserting it in prose.

`write` and `delete` at level 0 were deliberately left alone. The housing role keeps the
record; it just stops seeing one column.

THE MECHANISM, because it is not the one people expect
------------------------------------------------------
A level violation on WRITE does not raise. `Document.save` calls
`validate_higher_perm_levels()` (frappe/model/document.py:412) BEFORE `run_before_save_methods`
(:414) and `_validate` (:417). For an existing document that lands in
`reset_values_if_no_permlevel_access`, which takes the value from `self.get_latest()` — the
STORED row — and writes it back over whatever was submitted
(frappe/model/base_document.py:1288,1291). So an unprivileged write is SILENTLY REVERTED,
not refused, and the two verdicts this file asserts are "persisted" versus "reverted".

That is also why the housing role can still save: the field it cannot see is restored from
the database rather than blanked, so `Freelancer.validate`'s positive-salary check
(freelancer.py:39) sees the stored amount and passes. Had the framework blanked it instead,
every housing edit would have died on that check — which is exactly what happens on the
CREATE path, where the reference document is `frappe.new_doc` and the value really is empty.

Run under bench:
  bench --site <site> run-tests --module apex.logistay.doctype.freelancer.test_freelancer_salary_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

_FREELANCER_JSON = Path(__file__).resolve().parent / "freelancer.json"

FINANCE_ROLE = "Finance Manager"
HOUSING_ROLE = "Accommodation Manager"


class TestFreelancerSalaryPermlevel(FrappeTestCase):
    """Site-bound. Every fixture is minted per METHOD: rollback is rows-only and per-class,
    so a doc reused across methods would carry the previous method's mutations."""

    def setUp(self):
        # Restore the session BEFORE anything mutates it — frappe.session.user is process
        # state and no rollback touches it.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _user_with_role(self, role):
        """A fresh System User holding exactly one apex role.

        The hash is 12 wide on purpose: a short random fixture name collides across a long
        suite run and the collision surfaces as an unrelated DuplicateEntryError.
        """
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a298_{frappe.generate_hash(length=12)}@example.com",
                "first_name": role.split()[0],
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _freelance(self, salary=3000):
        return frappe.get_doc(
            {
                "doctype": "Freelancer",
                "full_name": "A298 Salary Subject",
                "national_id_or_iqama": f"ID{frappe.generate_hash(length=12)}",
                "contract_start_date": nowdate(),
                "contract_end_date": add_days(nowdate(), 180),
                "monthly_salary": salary,
            }
        ).insert(ignore_permissions=True)

    def test_finance_sets_the_salary_and_the_housing_role_cannot(self):
        """THE PAIR. Both verdicts in one method so they cannot drift apart, and asserted
        explicitly different at the end — a bug that reverted BOTH writes would otherwise
        satisfy the refusal half and look correct."""
        doc = self._freelance(salary=3000)
        finance = self._user_with_role(FINANCE_ROLE)
        housing = self._user_with_role(HOUSING_ROLE)

        # The access itself, before either write: 1 must be reachable for one and not the
        # other, or the two outcomes below would prove nothing about permlevels.
        frappe.set_user(finance)
        self.assertIn(
            1,
            frappe.get_doc("Freelancer", doc.name).get_permlevel_access("write"),
            f"{FINANCE_ROLE} lost its permlevel-1 write row",
        )
        frappe.set_user(housing)
        self.assertNotIn(
            1,
            frappe.get_doc("Freelancer", doc.name).get_permlevel_access("write"),
            f"{HOUSING_ROLE} must not reach permlevel 1",
        )

        # Verdict A — the privileged write PERSISTS.
        frappe.set_user(finance)
        privileged = frappe.get_doc("Freelancer", doc.name)
        privileged.monthly_salary = 7777
        privileged.save()
        finance_stored = frappe.db.get_value("Freelancer", doc.name, "monthly_salary")

        # Verdict B — the unprivileged write is REVERTED, silently, with no exception.
        frappe.set_user(housing)
        unprivileged = frappe.get_doc("Freelancer", doc.name)
        unprivileged.monthly_salary = 1
        unprivileged.save()  # must NOT raise: the framework reverts, it does not refuse
        housing_stored = frappe.db.get_value("Freelancer", doc.name, "monthly_salary")

        self.assertEqual(float(finance_stored), 7777.0, f"{FINANCE_ROLE} could not set the salary")
        self.assertEqual(
            float(housing_stored),
            7777.0,
            f"{HOUSING_ROLE} changed a permlevel-1 field it holds no row for",
        )
        self.assertNotEqual(
            float(housing_stored),
            1.0,
            "the unprivileged value landed — the permlevel is not being enforced on write",
        )
        # The explicit difference the card asked for: same field, same document, two roles,
        # two outcomes.
        self.assertNotEqual(
            (FINANCE_ROLE, 7777.0, "persisted"),
            (HOUSING_ROLE, float(housing_stored), "reverted" if housing_stored != 1 else "persisted"),
            "both roles produced the same verdict — the pair collapsed",
        )

    def test_the_housing_role_can_still_save_with_the_salary_intact(self):
        """The regression this move could plausibly have caused.

        `Freelancer.validate` throws on a non-positive salary (freelancer.py:39). If the
        framework blanked the unreadable field instead of restoring it, EVERY housing edit
        would die there. It restores from the stored row (base_document.py:1288,1291), and
        that happens at document.py:412, before validate at :414 — so the save survives.
        """
        doc = self._freelance(salary=4200)
        housing = self._user_with_role(HOUSING_ROLE)

        frappe.set_user(housing)
        maintained = frappe.get_doc("Freelancer", doc.name)
        maintained.status = "Terminated"
        maintained.save()

        self.assertEqual(
            frappe.db.get_value("Freelancer", doc.name, "status"),
            "Terminated",
            "the housing role lost the ability to maintain the record",
        )
        self.assertEqual(
            float(frappe.db.get_value("Freelancer", doc.name, "monthly_salary")),
            4200.0,
            "a save by a role that cannot SEE the salary wiped it — the restore path broke",
        )

    def test_a_save_that_never_touched_the_salary_still_keeps_it(self):
        """The stricter version: the incoming document has the attribute STRIPPED, which is
        what the Desk actually sends (frappe/desk/form/load.py:53 deletes it on read). The
        restore must cope with the field being absent, not merely wrong."""
        doc = self._freelance(salary=5100)
        housing = self._user_with_role(HOUSING_ROLE)

        frappe.set_user(housing)
        maintained = frappe.get_doc("Freelancer", doc.name)
        maintained.apply_fieldlevel_read_permissions()
        self.assertIsNone(
            maintained.get("monthly_salary"),
            "precondition: the read strip must have removed the field for this role",
        )
        maintained.status = "Expired"
        maintained.save()

        self.assertEqual(
            float(frappe.db.get_value("Freelancer", doc.name, "monthly_salary")),
            5100.0,
            "saving a document whose salary was stripped on read erased the stored value",
        )

    def test_the_housing_role_cannot_read_the_salary_through_the_api(self):
        """`write` was left alone, so the only thing that changed for this role is the read.
        Asserted through the API path, since that is where the strip lives — an in-process
        `frappe.get_doc` does NOT strip (only frappe/client.py:110, desk/form/load.py:53,
        api/v1.py:81 and api/v2.py do), and asserting on the raw doc would prove nothing.

        The strip deletes the attribute (document.py:771), but `as_dict` rebuilds every
        column and coerces a float-like fieldtype with `flt()` (base_document.py:402), so a
        concealed Currency arrives as 0.0 where a concealed Data arrives as None. Assert
        the real salary is gone, not that the key is None — that would only ever pass for
        the Data field beside it."""
        doc = self._freelance(salary=6300)
        housing = self._user_with_role(HOUSING_ROLE)
        finance = self._user_with_role(FINANCE_ROLE)

        frappe.set_user(housing)
        stripped = frappe.client.get("Freelancer", doc.name)
        self.assertFalse(
            flt(stripped.get("monthly_salary")), f"{HOUSING_ROLE} can still read the salary"
        )
        self.assertIsNone(
            stripped.get("national_id_or_iqama"),
            "precondition: the pre-existing permlevel-1 PII must also be stripped",
        )
        self.assertEqual(
            stripped.get("status"), doc.status, "level-0 fields must survive the strip"
        )

        frappe.set_user(finance)
        visible = frappe.client.get("Freelancer", doc.name)
        self.assertEqual(
            float(visible.get("monthly_salary")),
            6300.0,
            f"{FINANCE_ROLE} lost the salary it is supposed to hold",
        )

    def test_the_move_added_no_permission_row(self):
        """The card's cost claim, checked against the shipped JSON rather than trusted.

        A permlevel-1 row is NOT a duplicate of the permlevel-0 row for the same role:
        `is_perm_applicable` keeps only permlevel-0 rows (frappe/permissions.py:284), so the
        two rows answer different questions and deduplicating on role alone would strip the
        field access this whole change depends on.
        """
        shipped = json.loads(_FREELANCER_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]
        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            {FINANCE_ROLE, "System Manager"},
            "the permlevel-1 role set changed — this move was supposed to cost no new row",
        )
        for role in high:
            row = [p for p in rows if p["role"] == role and int(p.get("permlevel") or 0) == 1]
            self.assertEqual(len(row), 1, f"{role}: expected exactly one permlevel-1 row")
            self.assertEqual(row[0].get("write"), 1, f"{role}: permlevel-1 write missing")
            self.assertEqual(row[0].get("read"), 1, f"{role}: permlevel-1 read missing")

        salary = [f for f in shipped["fields"] if f["fieldname"] == "monthly_salary"][0]
        self.assertEqual(salary.get("permlevel"), 1, "monthly_salary is not at permlevel 1")
        self.assertIn(
            "permlevel",
            (salary.get("description") or ""),
            "the field must carry WHY it sits at level 1, not just the setting",
        )

    def test_write_and_delete_at_level_zero_were_left_alone(self):
        """The explicit non-change. Only a field moved, not a role's authority."""
        shipped = json.loads(_FREELANCER_JSON.read_text(encoding="utf-8"))
        housing = [
            p
            for p in shipped["permissions"]
            if p["role"] == HOUSING_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(housing), 1)
        self.assertEqual(housing[0].get("write"), 1, "housing write was collateral damage")
        self.assertEqual(housing[0].get("delete"), 1, "housing delete was collateral damage")
