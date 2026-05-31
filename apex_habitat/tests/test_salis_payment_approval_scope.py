"""Project row-scoping regression tests for ``Salis Payment Request``.

The DocType carries a ``project`` Link field and is readable by the scoped
``Fleet Supervisor`` / ``Fleet Project Manager`` roles (which are NOT in
``UNSCOPED_ROLES``). Before this fix it was not registered in
``permission_query_conditions``, and its ``has_permission`` slot held a
segregation-of-duties function that only enforced maker != checker — it did no
project scoping.

THE EXACT LEAK SURFACE — project-less (NULL/blank ``project``) documents.
Frappe's native User-Permission engine independently restricts a Link field
(``project``) to the values the user is permitted, so a *wrong-project* row is
already filtered. But that native match deliberately ADMITS rows whose link is
empty: the generated SQL is ``(ifnull(`project`,'')='' OR `project` IN (...))``.
The already-scoped DocTypes (Fuel Request, Support Ticket) add a strict
``AND project IN (...)`` via their ``*_query`` hook precisely to close that NULL
hole, and their ``scoped_has_permission`` denies a project-less doc unless the
caller owns it. ``Salis Payment Request`` had NEITHER half, so a scoped
supervisor of project A could list and open EVERY project-less payment request
(and, via the same missing hook, any row the native match does not cover).

These tests lock the hole shut, the same way the other scoped DocTypes are
protected:

  * the live list query (``frappe.get_list`` exercises the real
    ``permission_query_conditions`` wiring) excludes a project-less row for a
    scoped user, while an oversight role (``Fleet Manager``) still sees it;
  * per-document ``has_permission`` (the function actually wired in hooks)
    DENIES a project-less / out-of-scope document while allowing an in-scope
    one;
  * the segregation-of-duties rule (requester/creator cannot authorize their
    own request into a Finance-exclusive / decision state) is NOT weakened by
    composing project scoping on top of it.

The read-leak assertions deliberately use project-less documents because that
is the surface the native engine leaves open and the app hook must close; a
wrong-project assertion would pass even without the fix (native matching catches
it) and so would not prove the hole.

The tests drive the permission layer the same way a real caller does
(``frappe.set_user`` + ``frappe.get_list`` / the hooked ``has_permission``
functions) rather than only the happy path.
"""

import unittest

import frappe

from apex_habitat.salis.permissions import payment_sod_has_permission
from apex_habitat.tests._helpers import _user


def _project(name):
    p = frappe.db.get_value("Project", {"project_name": name}, "name")
    if not p:
        p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
            ignore_permissions=True
        ).name
    return p


def _grant_project(user, project):
    if not frappe.db.exists(
        "User Permission", {"allow": "Project", "for_value": project, "user": user}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "allow": "Project",
                "for_value": project,
                "user": user,
            }
        ).insert(ignore_permissions=True)


def _payment_request(project=None):
    """A draft Salis Payment Request (no GL, no submit). ``project`` may be None
    to model the project-less leak surface."""
    doc = frappe.get_doc(
        {
            "doctype": "Salis Payment Request",
            "expense_type": "Other",
            "amount": 100,
            "project": project,
            "status": "Draft",
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


class TestSalisPaymentRequestScoping(unittest.TestCase):
    """A scoped supervisor sees only their project's payment requests."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.pa = _project("PayScope A")
        cls.pb = _project("PayScope B")
        # Fleet Supervisor has read but not submit -> ideal for read-leak tests.
        cls.sup = _user("payscope_sup@example.com", "Fleet Supervisor")
        _grant_project(cls.sup, cls.pa)
        # Unscoped oversight role: sees every project.
        cls.mgr = _user("payscope_mgr@example.com", "Fleet Manager")
        cls.pr_a = _payment_request(cls.pa)
        cls.pr_b = _payment_request(cls.pb)
        # The leak surface: a project-less request. Native User-Permission link
        # matching admits this row to every scoped user; only the app hook denies
        # it. Owned by Administrator so the "owner defers" branch never applies to
        # our scoped supervisor.
        cls.pr_null = _payment_request(None)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for pr in (cls.pr_a, cls.pr_b, cls.pr_null):
            frappe.delete_doc(
                "Salis Payment Request", pr.name, ignore_permissions=True, force=True
            )
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    # --- list view (permission_query_conditions) ---------------------------
    def test_list_excludes_projectless_for_scoped_user(self):
        """The true leak: a project-less row must NOT appear for a scoped user."""
        frappe.set_user(self.sup)
        names = {
            r["name"] for r in frappe.get_list("Salis Payment Request", fields=["name"])
        }
        self.assertIn(self.pr_a.name, names)
        self.assertNotIn(
            self.pr_null.name,
            names,
            "scoped supervisor must NOT see a project-less payment request",
        )
        # Defense in depth: a wrong-project row must also be excluded.
        self.assertNotIn(self.pr_b.name, names)

    def test_unscoped_manager_lists_all_projects(self):
        frappe.set_user(self.mgr)
        names = {r["name"] for r in frappe.get_list("Salis Payment Request", fields=["name"])}
        self.assertIn(self.pr_a.name, names)
        self.assertIn(self.pr_b.name, names)
        self.assertIn(
            self.pr_null.name, names, "oversight role must still see project-less rows"
        )

    # --- per-document has_permission (the function wired in hooks) ----------
    def test_doc_read_allowed_in_scope(self):
        frappe.set_user(self.sup)
        doc = frappe.get_doc("Salis Payment Request", self.pr_a.name)
        self.assertTrue(doc.has_permission("read"))

    def test_doc_read_denied_projectless(self):
        frappe.set_user(self.sup)
        # The wired has_permission must veto the project-less document for a
        # scoped user who does not own it.
        self.assertFalse(
            payment_sod_has_permission(
                frappe.get_doc("Salis Payment Request", self.pr_null.name),
                "read",
                user=self.sup,
            )
        )
        frappe.set_user(self.sup)
        self.assertFalse(
            frappe.has_permission(
                "Salis Payment Request", "read", doc=self.pr_null.name, user=self.sup
            ),
            "scoped supervisor must NOT be able to read a project-less payment request",
        )

    def test_doc_read_denied_wrong_project(self):
        frappe.set_user(self.sup)
        self.assertFalse(
            payment_sod_has_permission(
                frappe.get_doc("Salis Payment Request", self.pr_b.name),
                "read",
                user=self.sup,
            )
        )

    def test_unscoped_manager_reads_any_project(self):
        self.assertIsNone(
            payment_sod_has_permission(
                frappe.get_doc("Salis Payment Request", self.pr_b.name),
                "read",
                user=self.mgr,
            )
        )
        self.assertIsNone(
            payment_sod_has_permission(
                frappe.get_doc("Salis Payment Request", self.pr_null.name),
                "read",
                user=self.mgr,
            )
        )


class TestScopingDoesNotWeakenSoD(unittest.TestCase):
    """Composing project scope onto the SoD hook must NOT relax maker != checker.

    The requester/creator must still be blocked from authorizing their own
    request into a Finance-exclusive / decision state, exactly as before. We use
    an in-scope project so a scope failure cannot be what produces the deny —
    the deny must come from the SoD rule itself.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.pa = _project("SoDScope A")
        # Fleet Project Manager: scoped, can submit -> the realistic self-approver.
        cls.requester = _user("sod_pm@example.com", "Fleet Project Manager")
        _grant_project(cls.requester, cls.pa)
        # A different in-scope user who legitimately may authorize.
        cls.other = _user("sod_pm_other@example.com", "Fleet Project Manager")
        _grant_project(cls.other, cls.pa)
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _payment_doc(self, status, requested_by=None, owner=None):
        return frappe._dict(
            {
                "doctype": "Salis Payment Request",
                "status": status,
                "project": self.pa,
                "requested_by": requested_by,
                "owner": owner,
            }
        )

    def test_payment_self_approval_still_blocked_in_scope(self):
        # In-scope project, but the requester tries to push it to a Finance state.
        doc = self._payment_doc("Approved by Finance", requested_by=self.requester)
        self.assertFalse(
            payment_sod_has_permission(doc, "submit", user=self.requester),
            "requester must NOT self-approve into a Finance-exclusive state",
        )
        doc2 = self._payment_doc("Paid", owner=self.requester)
        self.assertFalse(
            payment_sod_has_permission(doc2, "write", user=self.requester)
        )

    def test_payment_other_in_scope_user_may_approve(self):
        doc = self._payment_doc("Approved by Finance", requested_by=self.requester)
        self.assertIsNone(
            payment_sod_has_permission(doc, "submit", user=self.other),
            "a different in-scope user may authorize (not self-approval)",
        )


if __name__ == "__main__":
    unittest.main()
