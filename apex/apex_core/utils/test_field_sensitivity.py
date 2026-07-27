# Copyright (c) 2026, AFMCO and contributors
"""The guard that reds when a sensitive field ships at permlevel 0.

The model is ``field_sensitivity``; read its docstring first, because this file only
ENFORCES the categories stated there. Site-free: it reads the shipped DocType JSON off
disk, so it runs the same under bench and under plain ``unittest``.

Four properties:

1. THE MODEL IS ENFORCED — every sensitive field still at level 0 must be a named,
   reasoned entry in ``KNOWN_LEVEL_ZERO_SENSITIVE``. Exact equality, like the sibling
   baseline in ``test_report_role_guard``: a NEW offender fails the build, a REPAIRED one
   must be pruned. This is the ratchet the card asked for.
2. A PLANTED FIELD REDS — ``TestAPlantedFieldIsCaught`` synthesises exactly the change an
   engineer would make (a new sensitive field at level 0, in each of the five categories)
   and asserts the guard names it. Without this the baseline test could pass simply by
   never detecting anything.
3. THE DETECTOR CAN FAIL — each category has a control that must stay clean (the same name
   on a non-person record, the same word at the wrong fieldtype), and
   ``test_dropping_the_person_master_gate_floods_the_baseline`` reproduces the classifier
   with that one gate removed and shows it goes from a handful to a flood — proving the
   gate is what makes the guard usable rather than muted.
4. THE MEASUREMENT IS REAL — ``TestTheModelMatchesTheShippedTree`` recomputes the adoption
   numbers quoted in the model's docstring, so the premise cannot rot silently.

DRAINED SO FAR, each with a colocated proof named after it: ``Freelancer.monthly_salary``,
then four signatures — on Housing Assignment, Custody Issue, Custody Acknowledgment and
Facility Asset Custody Assignment. Every level-1 row there carries WRITE, not merely read,
because those fields are set on a CREATE path, where a new document resolves an unreachable
level from ``frappe.new_doc`` — the default, not the stored row — so a read-only row empties
the signature on capture instead of protecting it. The portal case, Custody Acknowledgment,
is safe for a different reason: the Web Form insert bypasses levels (``web_form.py:663``).

Run standalone:  python3 -m unittest apex.apex_core.utils.test_field_sensitivity -v
"""

import copy
import sys
import types
import unittest

# Same stubbing idiom as test_report_role_guard: nothing here touches frappe, but the
# shipped_doctypes import sits under the apex package, which may pull frappe in.
if "frappe" not in sys.modules:
    sys.modules["frappe"] = types.ModuleType("frappe")

from apex.apex_core.utils import field_sensitivity  # noqa: E402
from apex.tests.shipped_doctypes import shipped_doctypes  # noqa: E402

# WHY EACH ENTRY IS STILL AT LEVEL 0. This model shipped with its guard and two worked
# examples; applying it module by module is deliberately later work, one reviewable change
# per module. Every entry below is an ACCEPTED EXPOSURE with a named owner decision behind
# it, not a bug someone forgot.
_SIGNATURES_NOT_YET_LAYERED = (
    "Category 1 (signature), not yet layered. Raising a Signature to level 1 needs a "
    "level-1 DocPerm row on this DocType for whichever role countersigns, and that role "
    "differs per custody flow — so each one is its own module change with its own reviewer. "
    "The exposure today: any role holding read on the record sees the captured mark."
)
_RESIDENT_REQUEST_PROSE = (
    "Category 5 (free text about a person). Resident Request is a person master and these "
    "three fields are exactly the unbounded prose the model warns about — a resident's own "
    "complaint text plus the triage and resolution notes written about them. They stay at "
    "level 0 because RAISING THEM WOULD PROTECT THEM FROM NOBODY, which is a different "
    "reason from the one this entry used to give. Every role holding read on this DocType "
    "already holds a permlevel-1 read row — all four of them, added when `mobile_number` "
    "was raised — so a level-1 wall here has nobody on the far side of it. "
    "`test_raising_the_resident_request_prose_would_shut_nobody_out` proves that off the "
    "shipped JSON rather than asserting it in prose, and will start failing the moment a "
    "role is given level-0 read without a level-1 row, which is the day raising these three "
    "fields starts buying something. Until then the flip is theatre with a real cost: "
    "`description` is `reqd`, and a required field at level 1 breaks create outright for "
    "any role lacking a level-1 write row. Closing this exposure needs a narrower read role "
    "to exist first, or an owner decision to accept it — not a field flip."
)

KNOWN_LEVEL_ZERO_SENSITIVE = {
    # Two left. The five already drained are listed in this module's docstring.
    "Vehicle Incident": ([("worker_signature", "signature")], _SIGNATURES_NOT_YET_LAYERED),
    "Resident Request": (
        [
            ("description", "free_text"),
            ("resolution_notes", "free_text"),
            ("triage_notes", "free_text"),
        ],
        _RESIDENT_REQUEST_PROSE,
    ),
}

# A minimal person master: a self-owned full_name is what makes it one.
_PERSON_MASTER = {
    "doctype": "DocType",
    "name": "_A303 Person",
    "fields": [{"fieldname": "full_name", "fieldtype": "Data", "label": "Full Name"}],
}
# A minimal operational record that merely REFERENCES a person.
_OPERATIONAL = {
    "doctype": "DocType",
    "name": "_A303 Work Order",
    "fields": [
        {"fieldname": "employee", "fieldtype": "Link", "options": "Employee"},
        {
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "fetch_from": "employee.employee_name",
        },
    ],
}

# One planted field per category, at level 0, exactly as an engineer would first write it.
PLANTED = {
    "signature": {"fieldname": "witness_signature", "fieldtype": "Signature"},
    "government_id": {"fieldname": "national_id_or_iqama", "fieldtype": "Data"},
    "personal_contact": {"fieldname": "mobile_number", "fieldtype": "Data"},
    "per_person_pay": {"fieldname": "monthly_salary", "fieldtype": "Currency"},
    "free_text": {"fieldname": "case_notes", "fieldtype": "Small Text"},
}


def _with_field(base, field):
    """A copy of ``base`` carrying one extra field."""
    out = copy.deepcopy(base)
    out["fields"] = out["fields"] + [dict(field)]
    return out


class TestAPlantedFieldIsCaught(unittest.TestCase):
    """Proof 2 — plant the offending field and watch the guard red."""

    def test_every_category_is_caught_at_level_zero(self):
        for category, field in PLANTED.items():
            with self.subTest(category=category):
                doc = _with_field(_PERSON_MASTER, field)
                found = field_sensitivity.offenders({doc["name"]: doc})
                self.assertEqual(
                    found,
                    {doc["name"]: [(field["fieldname"], category)]},
                    f"a level-0 {category} field was NOT caught",
                )

    def test_the_same_field_at_level_one_is_clean(self):
        """The control that makes proof 2 mean something: the guard must go quiet once the
        engineer does the right thing, or it is just asserting the field exists."""
        for category, field in PLANTED.items():
            with self.subTest(category=category):
                raised = dict(field, permlevel=1)
                doc = _with_field(_PERSON_MASTER, raised)
                self.assertEqual(field_sensitivity.offenders({doc["name"]: doc}), {})

    def test_a_planted_field_reds_the_shipped_baseline_assertion(self):
        """The end-to-end shape: the real tree plus one planted field no longer equals the
        frozen baseline, which is what makes the build fail for the next engineer."""
        doctypes = shipped_doctypes()
        self.assertEqual(
            _baseline_shape(field_sensitivity.offenders(doctypes)),
            _expected_shape(),
            "precondition: the shipped tree must match the baseline before planting",
        )
        doctypes[_PERSON_MASTER["name"]] = _with_field(
            _PERSON_MASTER, PLANTED["per_person_pay"]
        )
        self.assertNotEqual(
            _baseline_shape(field_sensitivity.offenders(doctypes)),
            _expected_shape(),
            "planting a level-0 salary field did not change the guard's verdict",
        )


class TestTheDetectorCanFail(unittest.TestCase):
    """Proof 3 — controls, and a mutant that shows the person gate is load-bearing."""

    def test_a_contextual_field_on_an_operational_record_is_not_flagged(self):
        """`mobile_number` on a company SIM, `completion_notes` on a work order: the same
        names the model deliberately leaves at level 0."""
        for category in ("personal_contact", "per_person_pay", "free_text"):
            with self.subTest(category=category):
                doc = _with_field(_OPERATIONAL, PLANTED[category])
                self.assertEqual(field_sensitivity.offenders({doc["name"]: doc}), {})

    def test_an_absolute_field_on_an_operational_record_IS_flagged(self):
        """Control for the control — the person gate must NOT suppress the absolute two."""
        for category in ("signature", "government_id"):
            with self.subTest(category=category):
                doc = _with_field(_OPERATIONAL, PLANTED[category])
                self.assertTrue(
                    field_sensitivity.offenders({doc["name"]: doc}),
                    f"{category} was wrongly gated behind the person-master test",
                )

    def test_a_policy_percent_named_salary_is_not_flagged(self):
        """`global_max_percent_of_salary` is a rule, not a person's pay. The Currency
        requirement is what keeps the whole Salary Deduction Policy tree out."""
        doc = _with_field(
            _PERSON_MASTER, {"fieldname": "global_max_percent_of_salary", "fieldtype": "Percent"}
        )
        self.assertEqual(field_sensitivity.offenders({doc["name"]: doc}), {})

    def test_a_layout_break_named_salary_is_not_flagged(self):
        """Section/Column breaks carry no value; frappe skips them too
        (display_fieldtypes, frappe/model/base_document.py:1270)."""
        doc = _with_field(
            _PERSON_MASTER, {"fieldname": "salary_section", "fieldtype": "Section Break"}
        )
        self.assertEqual(field_sensitivity.offenders({doc["name"]: doc}), {})

    def test_a_fetched_name_does_not_make_a_record_a_person_master(self):
        """The gate's own control: `employee_name` fetched from a Link must not promote an
        operational record, or every work order becomes a person master."""
        self.assertFalse(field_sensitivity.is_person_master(_OPERATIONAL))
        self.assertTrue(field_sensitivity.is_person_master(_PERSON_MASTER))

    def test_dropping_the_person_master_gate_floods_the_baseline(self):
        """The mutant. With the gate removed the contextual categories fire on every
        operational record, and the guard becomes a wall of noise nobody would keep. The
        real baseline is small BECAUSE the gate is there."""
        doctypes = shipped_doctypes()
        honest = sum(len(v) for v in field_sensitivity.offenders(doctypes).values())
        blind = 0
        for data in doctypes.values():
            for field in data.get("fields") or []:
                if field_sensitivity.categorise(field, person_master=True) and not int(
                    field.get("permlevel") or 0
                ):
                    blind += 1
        self.assertGreater(
            blind,
            honest * 4,
            f"the mutant found {blind} vs the real {honest}; the person gate is not "
            "actually doing the filtering this guard's usability depends on",
        )


def _baseline_shape(found):
    return {name: sorted(fields) for name, fields in found.items()}


def _expected_shape():
    return {name: sorted(fields) for name, (fields, _why) in KNOWN_LEVEL_ZERO_SENSITIVE.items()}


class TestTheModelIsEnforcedOnTheShippedTree(unittest.TestCase):
    """Proof 1 — the ratchet."""

    # Without this unittest elides the diff to "[487 chars]" and the failure names no
    # field, which is the difference between a guard an engineer can act on and one they
    # mute. Verified by planting a field and reading the output.
    maxDiff = None

    def setUp(self):
        self.doctypes = shipped_doctypes()

    def test_the_scan_sees_the_shipped_tree(self):
        self.assertGreaterEqual(
            len(self.doctypes), 150, "the DocType loader broke — the guard would pass empty"
        )

    def test_no_unlisted_sensitive_field_ships_at_level_zero(self):
        self.assertEqual(
            _baseline_shape(field_sensitivity.offenders(self.doctypes)),
            _expected_shape(),
            "field sensitivity changed. A NEW entry means a field this file's model calls "
            "personal or financial is readable by every role that can open the record — "
            "give it \"permlevel\": 1 and make sure some role holds a permlevel-1 DocPerm "
            "row, or, if the model is wrong for this field, argue that in "
            "field_sensitivity.py rather than adding an entry here. A MISSING entry means "
            "one was repaired and this baseline must shrink to match.",
        )

    def test_every_frozen_entry_carries_a_reason(self):
        for name, (fields, why) in KNOWN_LEVEL_ZERO_SENSITIVE.items():
            with self.subTest(doctype=name):
                self.assertTrue(fields, f"{name} is frozen with no field named")
                self.assertTrue(why and why.strip(), f"{name} is frozen with no reason")

    def test_no_frozen_entry_names_a_doctype_that_stopped_shipping(self):
        phantom = sorted(set(KNOWN_LEVEL_ZERO_SENSITIVE) - set(self.doctypes))
        self.assertEqual(phantom, [], "the baseline names DocType(s) this app no longer ships")

    def test_raising_the_resident_request_prose_would_shut_nobody_out(self):
        """The Resident Request entry's reason, made falsifiable.

        That entry used to say the three prose fields were unraised because raising them
        would need the housing roles given level-1 rows. They already have them: all four
        roles that hold read on this DocType also hold a permlevel-1 read row, added when
        `mobile_number` was raised. So the flip protects nobody, and the entry's real reason
        is that there is no role on the far side of the wall — not that the wall is
        expensive to build.

        A reason left in prose rots silently and the next reader does unnecessary work, or
        worse, does the flip and believes an exposure was closed. This asserts the fact
        instead. It fails the day someone grants level-0 read without a level-1 row, which
        is exactly the day raising these fields starts to buy something — at which point
        the entry should be drained rather than re-explained.

        Read is what matters here: a role that cannot READ the prose cannot leak it,
        whatever its write rows say.
        """
        request = self.doctypes["Resident Request"]
        rows = request["permissions"]
        can_read = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 0 and p.get("read")}
        reach_level_1 = {
            p["role"] for p in rows if int(p.get("permlevel") or 0) == 1 and p.get("read")
        }
        self.assertTrue(can_read, "Resident Request ships no level-0 read row at all")
        self.assertEqual(
            can_read - reach_level_1,
            set(),
            "a role now reads Resident Request without a permlevel-1 row, so raising "
            "description/triage_notes/resolution_notes would finally hide them from "
            "someone. Drain the baseline entry and do the flip — but note description is "
            "`reqd`, so that role needs a permlevel-1 WRITE row too or its create breaks.",
        )

    def test_the_freelancer_salary_stayed_drained(self):
        """The Freelancer salary fix raised it and pruned its entry. If either half
        regresses, say so here rather than letting the exact-equality diff explain it
        obliquely."""
        self.assertNotIn(
            "Freelancer",
            KNOWN_LEVEL_ZERO_SENSITIVE,
            "the Freelancer entry came back — the salary was un-raised, or re-frozen "
            "instead of fixed",
        )
        raised = dict(
            (fieldname, permlevel)
            for fieldname, _cat, permlevel in field_sensitivity.sensitive_fields(
                self.doctypes["Freelancer"]
            )
        )
        self.assertEqual(
            raised.get("monthly_salary"), 1,
            "the Freelancer monthly_salary fix regressed: the salary is back at level 0"
        )

class TestTheModelMatchesTheShippedTree(unittest.TestCase):
    """Proof 4 — the adoption numbers quoted in field_sensitivity's docstring."""

    def setUp(self):
        self.doctypes = shipped_doctypes()

    def test_the_quoted_adoption_numbers_still_hold(self):
        total = len(self.doctypes)
        with_high_field = sum(
            1
            for d in self.doctypes.values()
            if any(int(f.get("permlevel") or 0) > 0 for f in d.get("fields") or [])
        )
        with_high_row = sum(
            1
            for d in self.doctypes.values()
            if any(int(p.get("permlevel") or 0) > 0 for p in d.get("permissions") or [])
        )
        self.assertEqual(
            (total, with_high_field, with_high_row),
            (153, 23, 20),
            "the adoption numbers in field_sensitivity.py's docstring are stale — update "
            "the docstring and this assertion together, so the premise cannot rot.",
        )

    def test_a_person_master_is_rare(self):
        """The gate must stay narrow or the contextual categories flood."""
        masters = [n for n, d in self.doctypes.items() if field_sensitivity.is_person_master(d)]
        self.assertLess(
            len(masters),
            15,
            f"{len(masters)} person masters — the gate widened and the guard will get noisy",
        )


if __name__ == "__main__":
    unittest.main()
