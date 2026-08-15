# Copyright (c) 2026, AFMCO and contributors
"""A-229 — the create-path ordering hazard in ``company_scoped_has_permission``.

``Document.insert`` runs ``check_permission("create")`` (frappe/model/document.py:300)
BEFORE ``_validate_links()`` (:302) applies ``fetch_from``. SIM Card fetches its ``company``
from ``telecom_contract.company`` and SIM Custody Assignment from ``sim_card.company``, so
at the create check the field is EMPTY, the handler read None and denied outright — a
company-scoped SIM Operations User could not register a card under their OWN company.
Marking ``company`` ``reqd`` does not help: mandatory fields are enforced in ``_validate()``
(:310), long after the permission check.

Every test proves the fix BOTH ways: the fetched field empty and the anchor IN company must
defer, and the same shape on an out-of-company parent must still be refused.

WHY THESE TESTS ARE SITELESS. The bench is shared, so nothing here touches a site: the two
module-level resolvers are stubbed (the documented stub point) and ``frappe.db.get_value``
is a constructed lookup over the tables below.

A RUNTIME DEMONSTRATION IS THEREFORE STILL OWED: log in as a SIM Operations User holding a
User Permission for one company, create a SIM Card server-side against a contract in that
company with ``company`` unset, and confirm it saves while a contract in another company
raises PermissionError.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from apex.logistay import permissions as LP

ANCHORED = {dt: anchor for dt, anchor in LP.COMPANY_SCOPE.items() if anchor}

CO_A = "AFMCO A"
CO_B = "AFMCO B"

PARENTS = {
    "Telecom Contract": {"TC-A": CO_A, "TC-B": CO_B, "TC-NONE": None},
    "SIM Card": {"SIM-A": CO_A, "SIM-B": CO_B, "SIM-NONE": None},
}

_ABSENT = object()


def _anchor_names(parent_doctype):
    """The (in-company, out-of-company) parent for a doctype."""
    rows = PARENTS[parent_doctype]
    return (
        next(n for n, c in rows.items() if c == CO_A),
        next(n for n, c in rows.items() if c == CO_B),
    )


class _ScopeCase(unittest.TestCase):
    """A constructed session, db and scope, and no site anywhere."""

    def setUp(self):
        self._stub_local("session", frappe._dict(user="sim@example.com"))
        self._stub_local("db", SimpleNamespace(get_value=self._get_value))

    def _stub_local(self, name, value):
        """Install a stub on ``frappe.local``, queueing its restore BEFORE the write.

        `frappe.db` / `frappe.session` are proxies onto `frappe.local`, so a stub left
        installed is inherited by every later test in the run; registering the cleanup
        after the mutation would strand it if anything in between throws.
        """
        self.addCleanup(self._restore_local, name, getattr(frappe.local, name, _ABSENT))
        setattr(frappe.local, name, value)

    @staticmethod
    def _restore_local(name, original):
        """Absence is a value: werkzeug's ``Local`` raises for an unset name, so leaving
        ``None`` behind is not the same as never having stubbed."""
        if original is _ABSENT:
            try:
                delattr(frappe.local, name)
            except AttributeError:
                pass
        else:
            setattr(frappe.local, name, original)

    @staticmethod
    def _get_value(doctype, name, fieldname):
        if fieldname != "company":
            return None
        return PARENTS.get(doctype, {}).get(name)

    def scoped(self, companies=(CO_A,)):
        outer = patch.object(LP, "_is_unscoped", return_value=False)
        inner = patch.object(LP, "_allowed_companies", return_value=list(companies))
        outer.start()
        inner.start()
        self.addCleanup(inner.stop)
        self.addCleanup(outer.stop)
        self._stub_user_permissions(companies)

    def unscoped(self):
        outer = patch.object(LP, "_is_unscoped", return_value=True)
        outer.start()
        self.addCleanup(outer.stop)
        self._stub_user_permissions(())

    def _stub_user_permissions(self, companies):
        """Serve the ``applicable_for`` narrowing without a database.

        ``permission_scope.for_doctype`` re-reads frappe's own User Permission rows
        (permission_scope.py:104) to drop any value whose rows ALL name a different
        doctype. That read is real and is the point of the narrowing, so it is
        answered here with rows matching the scope this test already granted, each
        carrying no ``applicable_for`` — the row shape a plain company grant produces.
        """
        rows = {"Company": [{"doc": c, "applicable_for": None} for c in companies]}
        patcher = patch.object(
            frappe.permissions, "get_user_permissions", return_value=rows
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def doc(doctype, **kwargs):
        kwargs.setdefault("company", None)
        return SimpleNamespace(doctype=doctype, **kwargs)


class TestTheCreatePathResolvesThroughTheAnchor(_ScopeCase):
    """Proof 1 — a create with ``company`` still unfetched is decided on its merits."""

    def test_an_in_company_anchor_allows_the_create(self):
        self.scoped()
        for doctype, (field, parent_doctype) in ANCHORED.items():
            in_company, _out = _anchor_names(parent_doctype)
            with self.subTest(doctype=doctype):
                self.assertIsNone(
                    LP.company_scoped_has_permission(
                        self.doc(doctype, **{field: in_company}), "create"
                    ),
                    f"{doctype}: a scoped user cannot create under their own company",
                )

    def test_an_out_of_company_anchor_still_refuses_the_create(self):
        """The easy mistake this guards: making create pass by making it pass for all."""
        self.scoped()
        for doctype, (field, parent_doctype) in ANCHORED.items():
            _in, out = _anchor_names(parent_doctype)
            with self.subTest(doctype=doctype):
                self.assertIs(
                    LP.company_scoped_has_permission(
                        self.doc(doctype, **{field: out}), "create"
                    ),
                    False,
                    f"{doctype}: a scoped user created under another company",
                )

    def test_an_unresolvable_company_still_fails_closed(self):
        self.scoped()
        for doctype, (field, _parent) in ANCHORED.items():
            with self.subTest(doctype=doctype):
                self.assertIs(
                    LP.company_scoped_has_permission(
                        self.doc(doctype, **{field: None}), "create"
                    ),
                    False,
                )

    def test_the_two_verdicts_are_not_the_same_verdict(self):
        self.scoped()
        allowed = LP.company_scoped_has_permission(
            self.doc("SIM Card", telecom_contract="TC-A"), "create"
        )
        refused = LP.company_scoped_has_permission(
            self.doc("SIM Card", telecom_contract="TC-B"), "create"
        )
        self.assertEqual((allowed, refused), (None, False))


class TestTheAnchorNeverWidensAnythingElse(_ScopeCase):
    """Proof 2 — the fallback fires only where the fetched field is genuinely empty."""

    def test_a_populated_company_is_used_verbatim_and_the_anchor_ignored(self):
        """A stored row carries its own company; an in-company anchor must not rescue it."""
        self.scoped()
        self.assertIs(
            LP.company_scoped_has_permission(
                self.doc("SIM Card", company=CO_B, telecom_contract="TC-A"), "read"
            ),
            False,
        )

    def test_every_action_is_still_denied_out_of_company_not_just_create(self):
        self.scoped()
        for ptype in ("read", "write", "submit", "cancel", "delete"):
            with self.subTest(ptype=ptype):
                self.assertIs(
                    LP.company_scoped_has_permission(
                        self.doc("SIM Custody Assignment", sim_card="SIM-B"), ptype
                    ),
                    False,
                )

    def test_telecom_contract_carries_its_own_company_and_is_unchanged(self):
        """The parent doctype is not anchored: its ``company`` is a direct link."""
        self.scoped()
        self.assertIsNone(LP.COMPANY_SCOPE["Telecom Contract"])
        self.assertIsNone(
            LP.company_scoped_has_permission(
                SimpleNamespace(doctype="Telecom Contract", company=CO_A), "create"
            )
        )
        self.assertIs(
            LP.company_scoped_has_permission(
                SimpleNamespace(doctype="Telecom Contract", company=None), "create"
            ),
            False,
        )

    def test_a_scoped_user_holding_no_company_is_denied_through_the_anchor_too(self):
        self.scoped(companies=())
        self.assertIs(
            LP.company_scoped_has_permission(
                self.doc("SIM Card", telecom_contract="TC-A"), "create"
            ),
            False,
        )

    def test_oversight_defers_before_any_lookup_is_attempted(self):
        self.unscoped()
        self.assertIsNone(
            LP.company_scoped_has_permission(
                self.doc("SIM Card", telecom_contract="TC-B"), "create"
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
