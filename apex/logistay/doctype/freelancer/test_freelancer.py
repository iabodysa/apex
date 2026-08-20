# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Freelancer master: validation, the ID unique guard, the
permlevel-1 PII gate, and the accounting-party proof (Journal/Payment Entry)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from apex.tests import factories
import json
import unittest
from pathlib import Path
import apex
from apex.tests._helpers import _user, as_user
from frappe.utils import add_days, flt, nowdate


class TestFreelancer(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _doc(self, **overrides):
        data = {
            "doctype": "Freelancer",
            "full_name": "Test Freelancer",
            "national_id_or_iqama": f"ID{frappe.generate_hash(length=12)}",
            "contract_start_date": nowdate(),
            "contract_end_date": add_days(nowdate(), 180),
            "monthly_salary": 3000,
        }
        data.update(overrides)
        return frappe.get_doc(data)

    def test_saves_with_required_fields(self):
        doc = self._doc().insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("FRL-"))
        self.assertEqual(doc.status, "Active")

    def test_rejects_end_before_or_equal_start(self):
        with self.assertRaises(frappe.ValidationError):
            self._doc(contract_end_date=add_days(nowdate(), -1)).insert(
                ignore_permissions=True
            )

    def test_rejects_non_positive_salary(self):
        with self.assertRaises(frappe.ValidationError):
            self._doc(monthly_salary=0).insert(ignore_permissions=True)

    def test_status_derives_expired_for_past_contract(self):
        doc = self._doc(
            contract_start_date=add_days(nowdate(), -200),
            contract_end_date=add_days(nowdate(), -10),
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Expired")

    def test_rejects_duplicate_national_id(self):
        nid = f"ID{frappe.generate_hash(length=12)}"
        self._doc(national_id_or_iqama=nid).insert(ignore_permissions=True)
        with self.assertRaises(Exception):
            self._doc(national_id_or_iqama=nid).insert(ignore_permissions=True)

    def test_permlevel_pii_hidden_from_unprivileged_role(self):
        """A role with permlevel-0 read but no permlevel-1 read cannot see the PII.
        Internal Auditor reads at permlevel 0 only — the API strips national_id /
        mobile from its view."""
        doc = self._doc(mobile_number="0500000000").insert(ignore_permissions=True)

        user_id = f"freelance_auditor_{frappe.generate_hash(length=12)}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": user_id,
                "first_name": "Auditor",
                "roles": [{"role": "Internal Auditor"}],
            }
        ).insert(ignore_permissions=True)

        frappe.set_user(user.name)
        try:
            fetched = frappe.get_doc("Freelancer", doc.name)
            fetched.check_permission("read")
            fetched.apply_fieldlevel_read_permissions()
            stripped = fetched.as_dict()
            self.assertIsNone(stripped.get("national_id_or_iqama"))
            self.assertIsNone(stripped.get("mobile_number"))
            self.assertEqual(stripped.get("full_name"), "Test Freelancer")
        finally:
            frappe.set_user("Administrator")

    def _user_with_role(self, role):
        """A fresh System User holding exactly one apex role."""
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"freelance_{frappe.generate_hash(length=12)}@example.com",
                "first_name": role.split()[0],
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        return user.name

    def test_only_the_permlevel1_roles_can_create(self):
        """The pair, in one test so the two verdicts cannot collapse into one.

 Finance Manager holds create AND a permlevel-1 write row, so it
        can supply `national_id_or_iqama` and the insert lands. Accommodation
        Manager holds no permlevel-1 row, so its create was REMOVED rather than
        left to fail: `Document.insert` resets the unwritable PII to the
        `frappe.new_doc` value (empty) at document.py:306 before
        `_validate_mandatory` runs at :310, so a create button would raise
        MandatoryError on every single press.

        The refusal is caught by NAME: `frappe.PermissionError` does not descend
        from `ValidationError` (frappe/exceptions.py:34 vs :18), so the old
        MandatoryError could never satisfy this assertion.
        """
        self.addCleanup(frappe.set_user, "Administrator")
        finance = self._user_with_role("Finance Manager")
        housing = self._user_with_role("Accommodation Manager")

        # `has_permission` returns bool(perm) (frappe/permissions.py:193), so `assertIs`
        # is safe and 1 would not pass for True.
        self.assertIs(frappe.has_permission("Freelancer", "create", user=finance), True)
        self.assertIs(frappe.has_permission("Freelancer", "create", user=housing), False)
        # Only create was withdrawn — the housing role still maintains what exists.
        self.assertIs(frappe.has_permission("Freelancer", "read", user=housing), True)
        self.assertIs(frappe.has_permission("Freelancer", "write", user=housing), True)

        nid = f"ID{frappe.generate_hash(length=12)}"

        frappe.set_user(finance)
        created = self._doc(national_id_or_iqama=nid).insert()
        self.assertTrue(created.name.startswith("FRL-"))
        self.assertEqual(
            frappe.db.get_value("Freelancer", created.name, "national_id_or_iqama"),
            nid,
            "the permlevel-1 PII the create depends on must survive the reset pass",
        )
        self.assertIn(
            1,
            created.get_permlevel_access("write"),
            "Finance Manager must reach permlevel 1, or its create only appears to work",
        )

        frappe.set_user(housing)
        refused = self._doc(national_id_or_iqama=f"ID{frappe.generate_hash(length=12)}")
        self.assertNotIn(
            1,
            refused.get_permlevel_access("write"),
            "the housing role holds no permlevel-1 write — the reason create was "
            "removed instead of the PII boundary being widened",
        )
        with self.assertRaises(frappe.PermissionError):
            refused.insert()

    # The housing role's restore-on-update path for national_id_or_iqama is not asserted
    # here: it is a subTest of test_freelancer_salary_permlevel.py::
    # test_the_housing_role_can_still_save_with_every_level1_field_intact, which carries
    # both permlevel-1 fields beside the mechanism note (document.py:412 before :414,
    # base_document.py:1288,1291).

    def test_freelance_is_an_accounting_party(self):
        """The core proof: with the custom Party Type registered, a Journal Entry
        can carry party_type='Freelancer' + party=<a freelance>.

        This registration must not be gated behind a class-level ``skipUnless``:
        evaluated at IMPORT time, a skip would silently drop the one test that proves
        the shipped ``party_type.json`` fixture actually landed, on every run where it
        had not. Assert it: the Party Type is shipped by this app and erpnext is a
        required app, so a missing one is a fixture regression, not a portability
        concern.
        """
        self.assertTrue(
            frappe.db.exists("DocType", "Journal Entry"),
            "ERPNext Journal Entry must be installed — erpnext is a required app",
        )
        self.assertTrue(
            frappe.db.exists("Party Type", "Freelancer"),
            "the Freelancer Party Type must be registered — see apex/fixtures/party_type.json",
        )

        freelance = self._doc().insert(ignore_permissions=True)

        # Built, not skipped on: a fresh CI site's chart is not guaranteed
        # to carry a non-group Payable and Cash account in the company's base
        # currency, and without both there is no Journal Entry to hang the party on.
        company = factories.ensure_company()
        base_currency = frappe.db.get_value("Company", company, "default_currency")
        payable = factories.ensure_account(company, "Payable", "Liability", base_currency)
        cash = factories.ensure_account(company, "Cash", "Asset", base_currency)

        je = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "company": company,
                "posting_date": nowdate(),
                "accounts": [
                    {
                        "account": payable,
                        "party_type": "Freelancer",
                        "party": freelance.name,
                        "credit_in_account_currency": 3000,
                    },
                    {"account": cash, "debit_in_account_currency": 3000},
                ],
            }
        )
        je.set_missing_values()
        je.validate()
        self.assertEqual(je.accounts[0].party_type, "Freelancer")
        self.assertEqual(je.accounts[0].party, freelance.name)


# --- merged from test_freelancer_create_permission.py ---
_HERE = Path(apex.__file__).resolve().parent / "logistay" / "doctype" / "freelancer"
_APP_ROOT = _HERE.parents[2]
_DISPLAY_FIELDTYPES = frozenset(
    {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Fold", "Button"}
)
def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
def _permlevel(row: dict) -> int:
    return int(row.get("permlevel") or 0)
def _blocking_reqd_fields(doctype: dict) -> list[dict]:
    """Mandatory fields above permlevel 0 that a create must supply itself.

    A field with a `default` is exempt: `reset_values_if_no_permlevel_access`
    restores it from `frappe.new_doc`, which applies the default, so the
    mandatory check still passes.
    """
    return [
        f
        for f in doctype.get("fields") or []
        if f.get("reqd")
        and _permlevel(f) > 0
        and f.get("fieldtype") not in _DISPLAY_FIELDTYPES
        and not f.get("default")
    ]
def _unusable_create_grants(doctype: dict) -> list[str]:
    """`role -> fields it can never fill` for every create grant that cannot complete."""
    perms = doctype.get("permissions") or []
    blocking = _blocking_reqd_fields(doctype)
    if not blocking:
        return []
    offenders = []
    for role in sorted({p["role"] for p in perms if p.get("create") and _permlevel(p) == 0}):
        writable = {_permlevel(p) for p in perms if p.get("role") == role and p.get("write")}
        blocked = [f["fieldname"] for f in blocking if _permlevel(f) not in writable]
        if blocked:
            offenders.append(
                f"{doctype['name']}: {role!r} has create=1 but no write row at permlevel "
                f"{sorted({_permlevel(f) for f in blocking if f['fieldname'] in blocked})} "
                f"-> can never supply {sorted(blocked)}"
            )
    return offenders
def _app_doctypes():
    """Every DocType JSON shipped by the app, as (path, parsed) pairs."""
    for jp in sorted(_APP_ROOT.glob("**/doctype/*/*.json")):
        if jp.stem != jp.parent.name:
            continue
        try:
            data = _load(jp)
        except (ValueError, OSError):
            continue
        if data.get("doctype") == "DocType" and data.get("name"):
            yield jp, data
class TestEveryAppDocTypeCreateGrantIsUsable(unittest.TestCase):
    """The invariant across every DocType the app ships: a role with `create` can
    always complete it. No per-DocType behavioural substitute scales to 50+
    DocTypes and every role that holds `create` on each of them."""

    def test_scan_reaches_the_shipped_doctypes(self):
        names = {d["name"] for _, d in _app_doctypes()}
        self.assertGreater(len(names), 50, "DocType scan returned implausibly few files")
        self.assertIn("Freelancer", names)
        self.assertIn("Temporary Worker", names)

    def test_no_shipped_doctype_grants_a_create_that_cannot_complete(self):
        offenders = []
        for _, doctype in _app_doctypes():
            offenders.extend(_unusable_create_grants(doctype))
        self.assertEqual(
            sorted(offenders),
            [],
            "role(s) hold create on a DocType whose mandatory field sits above "
            "permlevel 0 with no matching write row — the create button is on the "
            "form and every press raises MandatoryError:\n" + "\n".join(sorted(offenders)),
        )
class TestInternalAuditorStaysOutOfFreelancerPii(FrappeTestCase):
    """The read-only role never reaches the permlevel-1 boundary the paying
    roles were given, asked live rather than off the DocPerm JSON.

    Companion to `test_freelancer.py::test_only_the_permlevel1_roles_can_create`,
    which proves who CAN create; this proves the read-only auditor can never
    widen into it. `frappe.has_permission` reads DocPerm, Custom DocPerm, User
    Permission and any `has_permission` hook together — a JSON read sees only
    one of the four.
    """

    AUDITOR = "freelancer_create_permission_auditor@example.com"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.auditor = _user(cls.AUDITOR, "Internal Auditor")

    def test_the_auditor_cannot_write_freelancer_and_reaches_no_permlevel_one_field(self):
        with as_user(self.auditor):
            self.assertTrue(
                frappe.has_permission("Freelancer", "read"),
                "Internal Auditor must still be able to read Freelancer",
            )
            for action in ("write", "create", "delete", "submit", "cancel", "amend"):
                self.assertFalse(
                    frappe.has_permission("Freelancer", action),
                    f"Internal Auditor must not be able to {action} Freelancer",
                )
            probe = frappe.new_doc("Freelancer")
            self.assertNotIn(
                1,
                probe.get_permlevel_access("write"),
                "Internal Auditor must not reach Freelancer's permlevel-1 PII fields "
                "— a role that cannot write at all must not appear to write PII either",
            )
if __name__ == "__main__":
    unittest.main()


# --- merged from test_freelancer_salary_permlevel.py ---
_FREELANCER_JSON = Path(apex.__file__).resolve().parent / "logistay" / "doctype" / "freelancer" / "freelancer.json"
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
        # two outcomes. Compare the VERDICTS alone. An earlier form compared
        # (role, value, verdict) triples, which could never be equal — the role names are
        # different literals — so it passed even when both verdicts read "persisted",
        # which is the one state it claimed to catch.
        finance_verdict = "persisted" if float(finance_stored) == 7777.0 else "reverted"
        housing_verdict = "persisted" if float(housing_stored) == 1.0 else "reverted"
        self.assertNotEqual(
            finance_verdict,
            housing_verdict,
            f"both roles produced the same verdict ({finance_verdict}) — the pair "
            "collapsed: either the permlevel stopped being enforced for anyone, or it "
            "is now enforced against Finance Manager too",
        )

    def test_the_housing_role_can_still_save_with_every_level1_field_intact(self):
        """The regression this move could plausibly have caused, over the WHOLE
        permlevel-1 section rather than the one field that moved.

        `Freelancer.validate` throws on a non-positive salary (freelancer.py:39). If the
        framework blanked the unreadable fields instead of restoring them, EVERY housing
        edit would die there. It restores from the stored row (base_document.py:1288,1291),
        and that happens at document.py:412, before validate at :414 — so the save
        survives and both concealed columns come back unchanged.

        This test and
        `test_freelancer.py::test_the_housing_role_can_still_maintain_an_existing_freelance`
        build the same fixture, make the same housing user, make the same status edit and
        the same save, differing only in which permlevel-1 field is read back —
        monthly_salary here, national_id_or_iqama there. Both checks run here as one
        subTest each, so neither verdict is lost.
        """
        nid = f"ID{frappe.generate_hash(length=12)}"
        doc = self._freelance(salary=4200)
        frappe.db.set_value("Freelancer", doc.name, "national_id_or_iqama", nid)
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
        for field, expected in (("monthly_salary", 4200.0), ("national_id_or_iqama", nid)):
            with self.subTest(field=field):
                stored = frappe.db.get_value("Freelancer", doc.name, field)
                self.assertEqual(
                    float(stored) if field == "monthly_salary" else stored,
                    expected,
                    f"a save by a role that cannot SEE {field} wiped it — the restore "
                    "path broke",
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

        The description is checked for MEANING, never for the literal token `permlevel`.
        That description is the tooltip a payroll clerk reads on the form, and user-facing
        text carries no system jargon — so a token probe could only ever pass on a
        description that leaked the setting's internal name into the clerk's face. The
        intent it was standing in for survives: the field must say WHO keeps the column
        and WHY, so a description that merely restates the restriction still fails here.
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
        described = (salary.get("description") or "").lower()
        for role in sorted(high):
            # The role's leading word, not its full name: the tooltip says "Finance",
            # which is how a clerk names the department that keeps the column.
            self.assertIn(
                role.split()[0].lower(),
                described,
                f"the description does not say {role} is who keeps the column",
            )
        self.assertIn(
            "only", described, "the description does not say the access is exclusive"
        )
        self.assertTrue(
            {"because", "so", "since"} & set(described.split()),
            "the description states the restriction but never says WHY it is restricted",
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
