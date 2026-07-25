# Copyright (c) 2026, AFMCO and contributors
"""Static surface guard for the native employee cost-recovery design (A-102).

Three of A-102's clauses are ABSENCE clauses — "there is exactly one accounting
path", "there are zero dangling references", "no new custom DocType was
introduced". An absence is proved by scanning the tree, not by exercising a
document, so this joins the pure-Python guard family (test_release_hygiene.py,
test_sql_interpolation_guard.py, test_duplicate_and_dead_code_guard.py): no
bench, no site, no fixtures.

Every check here is an ABSENCE assertion (plus one "exactly one" count), so a
safe refactor of the recovery engine cannot break it — only re-introducing a
second accounting path, a dangling Employee Deduction Acknowledgment reference,
or a bespoke DocType can.

Run standalone:  python3 -m unittest apex.tests.test_native_recovery_surface -v
"""

from __future__ import annotations

import glob
import json
import os
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# The retired consent DocType (Mahdar Iqrar) that A-102 replaced with the native
# Employee Advance chain, in both its human and its module spelling.
_RETIRED_DOCTYPE = "Employee Deduction Acknowledgment"
_RETIRED_SLUG = "employee_deduction_acknowledgment"

# [#a102ok] The ONLY places the retired name may still legitimately appear: the
# one-time drop patch that removes the orphaned metadata row from already-deployed
# sites (which must stay — see A-102's "the legacy patch stays" rule), its
# registration line in patches.txt, one sibling patch's docstring naming the
# engine it archives, and the released change-log entry that announced the
# removal. Anything else is a dangling reference.
_RETIRED_NAME_ALLOWLIST = frozenset(
    {
        os.path.join("patches", "v2_0", "drop_employee_deduction_acknowledgment.py"),
        os.path.join("patches", "v2_0", "archive_logistay_v1_engine.py"),
        "patches.txt",
        os.path.join("change_log", "v2", "v2_1_0.md"),
        # This guard itself has to name what it forbids.
        os.path.join("tests", "test_native_recovery_surface.py"),
    }
)

# [#a102ap] The employee-advance recovery engine and its one caller. Everything
# A-102 owns lives in these two files.
_RECOVERY_ENGINE = os.path.join("apex_core", "utils", "employee_recovery.py")
_RECOVERY_CALLER = os.path.join("salis", "doctype", "vehicle_incident", "vehicle_incident.py")

# [#a102np] Accounting primitives the recovery engine must NEVER post itself. The
# company payment is raised exclusively through HRMS's own Employee Advance
# "make_bank_entry" button, so apex owns no second GL path.
_FORBIDDEN_ACCOUNTING_TOKENS = (
    '"Journal Entry"',
    "'Journal Entry'",
    '"Payment Entry"',
    "'Payment Entry'",
    '"GL Entry"',
    "'GL Entry'",
    "make_gl_entries(",
    # HRMS's own payment button. Naming it in prose is the design note; CALLING
    # it from apex would be apex owning the payment.
    "make_bank_entry(",
)

# [#a102nb] Balance fields HRMS itself maintains. apex reads them to decide how
# much is still recoverable; writing one would be a second, competing ledger.
_NATIVE_BALANCE_WRITES = (
    'frappe.db.set_value("Employee Advance"',
    "frappe.db.set_value('Employee Advance'",
    'db_set("paid_amount"',
    'db_set("return_amount"',
    'db_set("claimed_amount"',
)

_TEXT_SUFFIXES = (".py", ".js", ".json", ".txt", ".csv", ".md", ".html", ".vue", ".ts")


def _rel(path):
    return os.path.relpath(path, APP_ROOT)


def _text_files():
    """Every human-readable file shipped inside the apex package."""
    out = []
    for path in sorted(glob.glob(os.path.join(APP_ROOT, "**", "*"), recursive=True)):
        if not os.path.isfile(path) or "node_modules" in path:
            continue
        if path.endswith(_TEXT_SUFFIXES):
            out.append(path)
    return out


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _doctype_json_paths():
    """Every <module>/doctype/<slug>/<slug>.json shipped by apex."""
    out = []
    for path in sorted(
        glob.glob(os.path.join(APP_ROOT, "*", "doctype", "*", "*.json"), recursive=False)
    ):
        slug = os.path.basename(os.path.dirname(path))
        if os.path.basename(path) == slug + ".json":
            out.append(path)
    return out


class TestNoDanglingRetiredDoctypeReference(unittest.TestCase):
    """A-102 clause: all Employee Deduction Acknowledgment references are migrated
    or removed — no dangling imports, hooks, links, tests or metadata."""

    def test_scan_reads_the_package(self):
        # Non-vacuity: every assertion below is an absence, so prove the scan
        # actually walked a populated tree first.
        files = _text_files()
        self.assertGreater(len(files), 200, "package text scan found almost nothing — path broke")

    def test_no_retired_doctype_directory_remains(self):
        leftovers = sorted(
            _rel(p)
            for p in glob.glob(os.path.join(APP_ROOT, "*", "doctype", _RETIRED_SLUG))
        )
        self.assertEqual(
            leftovers, [], f"the retired {_RETIRED_DOCTYPE} DocType directory is back"
        )

    def test_no_retired_doctype_json_metadata_declares_it(self):
        """No shipped JSON (DocType field options, workflow, workspace link,
        notification, dashboard, report) may still point at the retired DocType."""
        offenders = []
        for path in _text_files():
            if not path.endswith(".json"):
                continue
            rel = _rel(path)
            if rel in _RETIRED_NAME_ALLOWLIST:
                continue
            if _RETIRED_DOCTYPE in _read(path) or _RETIRED_SLUG in _read(path):
                offenders.append(rel)
        self.assertEqual(
            sorted(offenders), [], f"JSON metadata still references {_RETIRED_DOCTYPE}"
        )

    def test_no_python_or_frontend_reference_outside_the_drop_patch(self):
        """The only surviving mentions are the one-time drop patch (which must
        stay for already-deployed sites), its patches.txt registration, one
        sibling patch docstring, and the released change-log entry."""
        offenders = []
        for path in _text_files():
            rel = _rel(path)
            if rel in _RETIRED_NAME_ALLOWLIST:
                continue
            body = _read(path)
            if _RETIRED_DOCTYPE in body or _RETIRED_SLUG in body:
                offenders.append(rel)
        self.assertEqual(
            sorted(offenders),
            [],
            f"dangling {_RETIRED_DOCTYPE} reference(s) outside the allowed drop-patch surface",
        )

    def test_the_drop_patch_is_still_registered(self):
        """The removal is a one-time patch, not a deletion: an already-deployed
        site still needs it to clear the orphaned metadata row."""
        patch_file = os.path.join(APP_ROOT, "patches", "v2_0", f"drop_{_RETIRED_SLUG}.py")
        self.assertTrue(os.path.exists(patch_file), "the drop patch module was removed")
        registered = _read(os.path.join(APP_ROOT, "patches.txt"))
        self.assertIn(
            f"apex.patches.v2_0.drop_{_RETIRED_SLUG}",
            registered,
            "the drop patch is no longer registered in patches.txt",
        )


class TestOneNativeEmployeeAdvancePath(unittest.TestCase):
    """A-102 clause: company payment uses ONE native employee-advance accounting
    path — HRMS's own. apex raises the receivable and schedules installments; it
    posts no GL, Journal or Payment Entry and never writes a balance field."""

    def _recovery_sources(self):
        sources = {}
        for rel in (_RECOVERY_ENGINE, _RECOVERY_CALLER):
            path = os.path.join(APP_ROOT, rel)
            self.assertTrue(os.path.exists(path), f"{rel} moved — update this guard")
            sources[rel] = _read(path)
        return sources

    def test_exactly_one_module_constructs_an_employee_advance(self):
        """Two constructors would be two receivable paths. Repo-wide count, so a
        new one anywhere in apex fails this."""
        builders = sorted(
            _rel(p)
            for p in _text_files()
            if p.endswith(".py")
            and not os.path.basename(p).startswith("test_")
            and '"doctype": "Employee Advance"' in _read(p)
        )
        self.assertEqual(
            builders,
            [_RECOVERY_ENGINE],
            "Employee Advance must be raised from exactly one module",
        )

    def test_recovery_modules_post_no_gl_journal_or_payment_entry(self):
        offenders = []
        for rel, body in self._recovery_sources().items():
            for token in _FORBIDDEN_ACCOUNTING_TOKENS:
                if token in body:
                    offenders.append(f"{rel}: {token}")
        self.assertEqual(
            sorted(offenders),
            [],
            "the recovery engine must post no accounting entry of its own — the "
            "company payment is raised through HRMS's own Employee Advance button",
        )

    def test_recovery_modules_never_write_a_native_balance_field(self):
        """paid_amount / return_amount / claimed_amount are HRMS's to maintain.
        apex reads them to decide how much is recoverable and writes none."""
        offenders = []
        for rel, body in self._recovery_sources().items():
            for token in _NATIVE_BALANCE_WRITES:
                if token in body:
                    offenders.append(f"{rel}: {token}")
        self.assertEqual(
            sorted(offenders),
            [],
            "the recovered balance is maintained natively by HRMS and must never "
            "be recomputed or written by apex",
        )

    def test_installments_are_linked_through_the_native_reference_fields(self):
        """ref_doctype / ref_docname are the keys HRMS's own
        update_return_amount_in_employee_advance reads — the installment must
        carry them or the native balance would never move."""
        engine = self._recovery_sources()[_RECOVERY_ENGINE]
        self.assertIn('"ref_doctype": "Employee Advance"', engine)
        self.assertIn('"ref_docname": advance', engine)


class TestNoBespokeRecoveryDoctype(unittest.TestCase):
    """A-102 clause: no new custom DocType is introduced. The source linkage on
    the advance ships as a Customization, and the recovery engine touches only
    native (frappe / erpnext / hrms) DocTypes."""

    def _apex_doctype_names(self):
        names = set()
        for path in _doctype_json_paths():
            try:
                data = json.loads(_read(path))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("name"):
                names.add(data["name"])
        return names

    def test_apex_ships_doctypes_at_all(self):
        # Non-vacuity guard for the two absence tests below.
        self.assertGreater(len(self._apex_doctype_names()), 50, "DocType scan broke")

    def test_the_engine_references_no_apex_owned_doctype(self):
        """Every DocType the engine names is native. An apex DocType appearing
        here would mean the native chain grew a bespoke record."""
        body = _read(os.path.join(APP_ROOT, _RECOVERY_ENGINE))
        used = sorted(
            name
            for name in self._apex_doctype_names()
            if f'"{name}"' in body or f"'{name}'" in body
        )
        self.assertEqual(
            used, [], "the native recovery chain must reference no apex-owned DocType"
        )

    def test_no_bespoke_advance_or_deduction_consent_doctype_is_shipped(self):
        """A bespoke advance record, or a bespoke wage-deduction consent record,
        is exactly what A-102 removed in favour of the native chain. (Habitat's
        unrelated Custody Acknowledgment is a custody handover receipt, not a
        wage-deduction consent, so the match is deliberately narrow.)"""
        offenders = sorted(
            name
            for name in self._apex_doctype_names()
            if "Advance" in name or "Deduction Acknowledg" in name
        )
        self.assertEqual(
            offenders,
            [],
            "a bespoke employee-advance / deduction-consent DocType was re-introduced",
        )

    def test_the_source_linkage_ships_as_a_customization(self):
        """custom_source_doctype / custom_source_document are Custom Fields on the
        NATIVE Employee Advance — the reason no new DocType was needed."""
        path = os.path.join(APP_ROOT, "apex_core", "custom", "employee_advance.json")
        self.assertTrue(os.path.exists(path), "the Employee Advance Customization is missing")
        data = json.loads(_read(path))
        self.assertEqual(data.get("doctype"), "Employee Advance")
        fields = {row.get("fieldname"): row for row in data.get("custom_fields") or []}
        for fieldname, fieldtype in (
            ("custom_source_doctype", "Link"),
            ("custom_source_document", "Dynamic Link"),
        ):
            self.assertIn(fieldname, fields, f"{fieldname} Customization is missing")
            self.assertEqual(fields[fieldname]["dt"], "Employee Advance")
            self.assertEqual(fields[fieldname]["fieldtype"], fieldtype)
            self.assertEqual(
                fields[fieldname].get("no_copy"),
                1,
                f"{fieldname} must be no_copy so an amendment cannot inherit the mapping",
            )


if __name__ == "__main__":
    unittest.main()
