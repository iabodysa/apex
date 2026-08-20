# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Safety Round controller.

Proves the duplicate guard fires for a repeated first round and that a marked
re-inspection is allowed as a second round, and that on_submit derives the
overall result from the linked Safety Task Execution statuses (worst wins):
a Not Done yields Fail, a Poor yields Needs Attention, all-good yields Pass.

TestSafetyRoundMakerChecker then drives the shipped desk surface as the REAL
roles rather than as the Administrator: the classes above insert with
``ignore_permissions=True``, so every one of them would stay green on a DocType
no operator could reach. It proves the maker/checker pair as a PAIR — one method
collects both verdicts and asserts they differ, so the separation cannot collapse
into everyone-refused and keep passing — plus the negative cases by MESSAGE.

TestNoDeprecatedInspectionReportSurface guards the other half of the flow's
reachability: the deprecated Safety Inspection Report must not be offered as a
competing operational entry point next to Safety Round. It is a frappe-free JSON
scan, which lives in test_safety_round_surface.py because this module imports
frappe and so cannot run standalone; that module checks the scan is
non-vacuous, because "found nothing" is what a broken glob also reports.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from apex.tests.factories import make_safety_round
import glob
import json
import os
import unittest
import apex


class TestSafetyRound(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"Round Bldg {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        self.task = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"SAF-RND-{tag}",
                "task_title": f"Round Task {tag}",
                "department": "Fire Safety",
                "frequency": "Weekly",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

    def _execution(self, safety_round, status):
        return frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": self.task,
                "execution_date": today(),
                "execution_status": status,
                "safety_round": safety_round,
            }
        ).insert(ignore_permissions=True)

    def test_duplicate_first_round_is_blocked(self):
        make_safety_round(self.building)
        with self.assertRaises(frappe.ValidationError):
            make_safety_round(self.building)

    def test_reinspection_second_round_is_allowed(self):
        make_safety_round(self.building)
        second = make_safety_round(self.building, is_reinspection=1)
        self.assertTrue(second.name, "a marked re-inspection must be accepted")

    def test_overall_result_fail_when_a_task_not_done(self):
        rnd = make_safety_round(self.building)
        self._execution(rnd.name, "Good").submit()
        self._execution(rnd.name, "Not Done").submit()
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.overall_result, "Fail")

    def test_overall_result_needs_attention_when_a_task_poor(self):
        rnd = make_safety_round(self.building)
        self._execution(rnd.name, "Good").submit()
        self._execution(rnd.name, "Poor").submit()
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.overall_result, "Needs Attention")

    def test_overall_result_pass_when_all_good(self):
        rnd = make_safety_round(self.building)
        self._execution(rnd.name, "Excellent").submit()
        self._execution(rnd.name, "Good").submit()
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.overall_result, "Pass")

    def _safety_update_call(self, pub):
        calls = [c for c in pub.call_args_list if c.args and c.args[0] == "safety_update"]
        self.assertEqual(len(calls), 1, "exactly one safety_update must be published")
        return calls[0]

    def test_submit_publishes_safety_update(self):
        rnd = make_safety_round(self.building)
        self._execution(rnd.name, "Good").submit()
        with patch.object(frappe, "publish_realtime") as pub:
            rnd.submit()
        args, kwargs = self._safety_update_call(pub)
        self.assertEqual(kwargs.get("doctype"), "Safety Round")
        self.assertTrue(kwargs.get("after_commit"))
        self.assertEqual(args[1].get("building"), self.building)
        self.assertEqual(args[1].get("action"), "submit")

    def test_cancel_publishes_safety_update(self):
        rnd = make_safety_round(self.building)
        execution = self._execution(rnd.name, "Good")
        execution.submit()
        rnd.submit()
        execution.cancel()
        with patch.object(frappe, "publish_realtime") as pub:
            rnd.cancel()
        args, kwargs = self._safety_update_call(pub)
        self.assertEqual(kwargs.get("doctype"), "Safety Round")
        self.assertTrue(kwargs.get("after_commit"))
        self.assertEqual(args[1].get("action"), "cancel")


def _h(n=12):
    """A collision-proof fixture suffix. Twelve chars, not the four a short hash
    gives: a per-method fixture set that collides reads as a duplicate-guard bug."""
    return frappe.generate_hash(length=n).upper()


class TestSafetyRoundMakerChecker(FrappeTestCase):
    """The maker/checker pair, driven as the real roles through the desk surface.

    Every other class in this file inserts as the Administrator with
    ``ignore_permissions=True``, which proves nothing about who can reach the
    record. These tests hold no such flag: the Safety Officer's own DocPerms and
    the building_scoped_has_permission hook decide every write, so a permission
    that stops shipping fails here.

    Scope model: neither Safety Officer nor Resident Supervisor sits in
    ``habitat.permissions.HOUSING_UNSCOPED_ROLES``, so BOTH are building-scoped
    and both need an explicit Building User Permission. A scoped user with no
    User Permission is denied every building (the fragment collapses to ``1=0``
    and the has_permission hook fails closed), which is what
    ``test_the_officer_cannot_reach_a_building_outside_their_scope`` pins.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.building = cls._building()
        cls.other_building = cls._building()
        cls.officer = cls._user("Safety Officer", cls.building)
        cls.checker = cls._user("Resident Supervisor", cls.building)
        cls.task = cls._task(evidence_required=0)
        cls.evidence_task = cls._task(evidence_required=1)

    @classmethod
    def _building(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "MC-" + _h(),
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role, building):
        """A user holding exactly ``role``, scoped to ``building`` by User Permission."""
        email = "mc-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Maker Checker",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        permission = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": email,
                "allow": "Building",
                "for_value": building,
            }
        )
        permission.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "User Permission",
            permission.name,
            force=True,
            ignore_permissions=True,
        )
        return email

    @classmethod
    def _task(cls, evidence_required):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": "MC-" + _h(),
                "task_title": "Maker Checker Task",
                "department": "Fire Safety",
                "frequency": "Daily",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "evidence_required": evidence_required,
                "is_active": 1,
            }
        )
        doc.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Safety Task Catalog",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _round(self, building=None, cadence=None):
        """A draft Safety Round inserted AS THE CURRENT USER — no ignore_permissions.

        Flagged ``is_reinspection`` because FrappeTestCase rolls back once per CLASS:
        sibling methods share the class-level building AND each other's rows, so a
        second plain round on the same (building, date, cadence) would hit the
        controller's duplicate guard and fail for a reason the test is not about.
        A re-inspection is the shipped way to record a legitimate second round, so
        this keeps the methods independent without weakening what is proven.
        """
        return frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": building or self.building,
                "round_date": today(),
                "cadence": cadence or "Daily",
                "is_reinspection": 1,
            }
        ).insert()

    def _execution(self, safety_round, status, task=None, building=None):
        """A draft Safety Task Execution inserted AS THE CURRENT USER."""
        return frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": building or self.building,
                "task": task or self.task,
                "execution_date": today(),
                "execution_status": status,
                "safety_round": safety_round,
            }
        ).insert()

    def _submit_verdict(self, round_name, user):
        """Re-fetch the round as ``user`` and report "submitted" or "refused".

        Re-fetched, never reused: ``Document._submit`` sets ``docstatus = 1`` on the
        in-memory object BEFORE ``save()`` runs the permission check, so a document
        left over from a refused submit is already dirty.

        ``frappe.PermissionError`` is caught BY NAME. A bare ``except`` here would
        report a genuine crash — a broken controller, a missing fixture — as the
        maker's refusal, which is the exact shape of green this whole class exists
        to prevent.
        """
        frappe.set_user(user)
        doc = frappe.get_doc("Safety Round", round_name)
        try:
            doc.submit()
        except frappe.PermissionError:
            return "refused"
        return "submitted"

    def test_the_officer_makes_the_draft_the_checker_submits_it_and_the_verdicts_differ(self):
        """The pair, proven as a pair.

        Both halves are collected as verdict strings and compared, so the test can
        never pass with the separation collapsed: if the DocPerms drifted to deny
        both roles, both verdicts would read "refused" and the final assertion
        fails, where two independent assertRaises would both still be satisfied.
        """
        frappe.set_user(self.officer)
        rnd = self._round()
        self.assertEqual(rnd.docstatus, 0, "the officer's round must save as a draft")
        self.assertTrue(
            frappe.db.exists("Safety Round", rnd.name),
            "the officer's draft must actually persist",
        )
        execution = self._execution(rnd.name, "Not Done")
        self.assertEqual(
            execution.docstatus,
            0,
            "the officer holds no submit on Safety Task Execution, so the "
            "evidence must stay a draft until a checker ratifies it",
        )

        maker = self._submit_verdict(rnd.name, self.officer)
        checker = self._submit_verdict(rnd.name, self.checker)

        self.assertEqual(maker, "refused", "the maker must not be able to submit")
        self.assertEqual(checker, "submitted", "the checker must be able to submit")
        self.assertNotEqual(
            maker,
            checker,
            "maker-checker collapsed: both roles reached the same verdict, so the "
            "separation is not being enforced by anything",
        )

        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value("Safety Task Execution", execution.name, "docstatus"),
            1,
            "the checker's submit must ratify the maker's draft evidence",
        )
        self.assertEqual(
            frappe.db.get_value("Safety Round", rnd.name, "overall_result"),
            "Fail",
            "a ratified Not Done must drive the result; reading only already-"
            "submitted rows would have closed this round as Pass",
        )

    def test_the_officer_cannot_reach_a_building_outside_their_scope(self):
        """The officer is scoped by User Permission to one building; the other one
        is refused at the create check, before the round exists."""
        frappe.set_user(self.officer)
        doc = frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": self.other_building,
                "round_date": today(),
                "cadence": "Daily",
            }
        )
        with self.assertRaises(frappe.PermissionError):
            doc.insert()

        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.count("Safety Round", {"building": self.other_building}),
            0,
            "no round may exist for a building the officer is scoped off",
        )

    def test_a_failed_task_needing_evidence_is_refused_by_message(self):
        """Missing evidence: a failing result on an evidence_required catalog task
        cannot be saved without a photo. Asserted on the MESSAGE, not the exception
        type — frappe's own link check raises ValidationError too, so a type-only
        assertion would pass on a round that never reached the controller."""
        frappe.set_user(self.officer)
        rnd = self._round()
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": self.evidence_task,
                "execution_date": today(),
                "execution_status": "Poor",
                "safety_round": rnd.name,
            }
        )
        with self.assertRaises(frappe.ValidationError) as caught:
            doc.insert()
        self.assertIn("must carry a photo", str(caught.exception))

    def test_a_passing_result_on_the_same_task_still_saves(self):
        """The lookalike for the guard above: the evidence rule is scoped to a
        FAILING result, so the same evidence_required task saves clean when the
        outcome passes. Without this the guard could be a blanket refusal and read
        as correct."""
        frappe.set_user(self.officer)
        rnd = self._round()
        doc = self._execution(rnd.name, "Good", task=self.evidence_task)
        self.assertEqual(doc.docstatus, 0)
        self.assertTrue(frappe.db.exists("Safety Task Execution", doc.name))

    def test_a_round_with_no_rated_task_is_refused_by_message(self):
        """Missing ratings: an unrated round derives "Pass" from an empty status
        set — a signed-off record claiming the building was checked and sound when
        nothing was checked. Run as the CHECKER, who HOLDS submit, so a
        PermissionError cannot masquerade as this guard."""
        frappe.set_user(self.checker)
        rnd = self._round()
        with self.assertRaises(frappe.ValidationError) as caught:
            rnd.submit()
        self.assertIn("no rated safety task", str(caught.exception))

        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value("Safety Round", rnd.name, "docstatus"),
            0,
            "a refused submit must leave the round a draft",
        )

    def test_the_same_round_submits_once_a_task_is_rated(self):
        """The lookalike for the ratings guard: identical to the refusal above
        except that one execution exists, so the guard cannot simply be blocking
        every submit."""
        frappe.set_user(self.checker)
        rnd = self._round()
        self._execution(rnd.name, "Good")
        rnd.submit()
        rnd.reload()
        self.assertEqual(rnd.docstatus, 1)
        self.assertEqual(rnd.overall_result, "Pass")



# --- merged from test_safety_round_surface.py ---
WORKSPACE_GLOB = os.path.join(
    os.path.dirname(os.path.abspath(apex.__file__)), "*", "workspace", "*", "*.json"
)
DEPRECATED_DOCTYPE = "Safety Inspection Report"
def workspace_links(pattern=WORKSPACE_GLOB):
    """[(workspace label, kind, target)] for every link and shortcut apex ships."""
    found = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or data.get("doctype") != "Workspace":
            continue
        label = data.get("label") or data.get("name")
        for row in data.get("links") or []:
            found.append((label, "link", row.get("link_to")))
        for row in data.get("shortcuts") or []:
            found.append((label, "shortcut", row.get("link_to")))
    return found
class TestNoDeprecatedInspectionReportSurface(unittest.TestCase):
    def setUp(self):
        self.links = workspace_links()

    def test_the_scan_is_non_vacuous(self):
        """"Nothing found" is also what a broken glob reports, so absence only
        means anything once the scan is shown to be reading real links."""
        self.assertGreaterEqual(
            len(self.links), 50, "the workspace JSON scan found almost nothing — glob broke"
        )
        # The workspace is "Housing and Safety"; a sentinel naming the retired "Safety"
        # workspace would fail for the wrong reason and hide whether the scan works.
        self.assertIn(
            ("Housing and Safety", "link", "Safety Round"),
            self.links,
            "the scan does not see the Safety Round link it is supposed to be "
            "guarding the neighbourhood of",
        )
        self.assertIn(
            ("Housing and Safety", "shortcut", "Safety Round"),
            self.links,
            "the scan does not read shortcut rows, so a deprecated shortcut "
            "would pass unseen",
        )

    def test_no_workspace_offers_the_deprecated_inspection_report(self):
        offenders = sorted(
            "{0} ({1})".format(label, kind)
            for label, kind, target in self.links
            if target == DEPRECATED_DOCTYPE
        )
        self.assertEqual(
            offenders,
            [],
            "{0} is deprecated in favour of Safety Round but is still offered as a "
            "workspace entry point by: {1}".format(DEPRECATED_DOCTYPE, offenders),
        )
if __name__ == "__main__":
    unittest.main()
