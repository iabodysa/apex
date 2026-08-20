# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver's level-1 PII had readers but no writer.

`national_id`, `driver_id`, `phone` and `license_number` sit at permlevel 1. The shipped
JSON granted Fleet Manager and System Manager a permlevel-1 row carrying `read` only, so
the two roles that are allowed to SEE the PII were the two roles whose edits to it were
thrown away. `write: 1` was added to both rows; nothing at permlevel 0 moved, and no role
gained a permlevel-1 row it did not already hold.

THE MECHANISM, because a level violation does not raise
-------------------------------------------------------
`Document._save` calls `validate_higher_perm_levels()` (frappe/model/document.py:412)
before `run_before_save_methods` (:414); `insert` calls it at :306. It hands off to
`reset_values_if_no_permlevel_access` (frappe/model/base_document.py:1263), which takes
the replacement value from the STORED row on an update and from `frappe.new_doc` on a
create (:1276-1288). So the failure mode was SILENT: an update reverted to the old value
and a create landed with the column empty. Never assert `assertRaises` here — assert the
stored value.

Both verdicts live in one method wherever they can, so a regression that reverted BOTH
writes cannot satisfy the refusal half and look correct.

Run under bench:
  bench --site <site> run-tests --module apex.salis.doctype.salis_driver.test_salis_driver_pii_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.tests._helpers import _grant_project, _project
import ast
import re
import unittest
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.salis import utils
from apex.salis.doctype.salis_driver import salis_driver

_DRIVER_JSON = Path(apex.__file__).resolve().parent / "salis" / "doctype" / "salis_driver" / "salis_driver.json"

FLEET_MANAGER = "Fleet Manager"
# Holds permlevel-0 write on Salis Driver and NO permlevel-1 row — the counter-case that
# keeps the positive verdict from being vacuous. Project-scoped, so it needs a User
# Permission or it would fail at the row check instead of the field check.
FLEET_SUPERVISOR = "Fleet Supervisor"

# The four fields the level-1 section actually holds. Asserted as a set below so a field
# quietly leaving the section is caught rather than silently narrowing this proof.
PII_FIELDS = {"national_id", "driver_id", "phone", "license_number"}


class TestSalisDriverPiiPermlevel(FrappeTestCase):
    """Site-bound. Fixtures are minted per METHOD: rollback covers rows only, so a doc
    reused across methods would carry the previous method's mutations."""

    def setUp(self):
        # frappe.session.user is process state — no rollback restores it.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        self.project = _project("S005 Driver PII Project")

    def _user_with_role(self, role):
        """A fresh System User holding exactly one apex role.

        Exactly one, because a permlevel proof is only as good as the role set behind it —
        a reused fixture user that had picked up a second role would grant level-1 access
        this test believes it withheld. The hash is 12 wide: a short fixture name collides
        across a long suite run and surfaces as an unrelated DuplicateEntryError.
        """
        return (
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": f"s005_{frappe.generate_hash(length=12)}@example.com",
                    "first_name": role.split()[0],
                    "send_welcome_email": 0,
                    "roles": [{"role": role}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _driver(self, **overrides):
        values = {
            "doctype": "Salis Driver",
            "full_name": "S005 PII Subject",
            "status": "Active",
            "project": self.project,
            "national_id": f"NID{frappe.generate_hash(length=12)}",
            "driver_id": f"DRV{frappe.generate_hash(length=12)}",
            "phone": "0500000000",
            "license_number": f"LIC{frappe.generate_hash(length=12)}",
        }
        values.update(overrides)
        return frappe.get_doc(values).insert(ignore_permissions=True)

    def test_the_fleet_manager_edit_persists_and_the_supervisor_edit_reverts(self):
        """THE PAIR. Same document, same two fields, two roles, two outcomes."""
        doc = self._driver()
        manager = self._user_with_role(FLEET_MANAGER)
        supervisor = self._user_with_role(FLEET_SUPERVISOR)
        _grant_project(supervisor, self.project)

        # The access itself, before either write — or neither outcome below would be
        # evidence about permlevels.
        frappe.set_user(manager)
        self.assertIn(
            1,
            frappe.get_doc("Salis Driver", doc.name).get_permlevel_access("write"),
            f"{FLEET_MANAGER} holds no permlevel-1 write row on Salis Driver",
        )
        frappe.set_user(supervisor)
        self.assertNotIn(
            1,
            frappe.get_doc("Salis Driver", doc.name).get_permlevel_access("write"),
            f"{FLEET_SUPERVISOR} must not reach permlevel 1",
        )

        # Verdict A — the privileged write PERSISTS.
        frappe.set_user(manager)
        privileged = frappe.get_doc("Salis Driver", doc.name)
        privileged.national_id = "1099887766"
        privileged.license_number = "LIC-S005-NEW"
        privileged.save()
        self.assertEqual(
            frappe.db.get_value("Salis Driver", doc.name, "national_id"),
            "1099887766",
            f"{FLEET_MANAGER}'s national_id edit was discarded — the permlevel-1 write row "
            "is missing or lost its write flag",
        )
        self.assertEqual(
            frappe.db.get_value("Salis Driver", doc.name, "license_number"),
            "LIC-S005-NEW",
            f"{FLEET_MANAGER}'s license_number edit was discarded",
        )

        # Verdict B — the unprivileged write is REVERTED, silently, with no exception.
        frappe.set_user(supervisor)
        unprivileged = frappe.get_doc("Salis Driver", doc.name)
        unprivileged.national_id = "2000000000"
        unprivileged.save()  # must NOT raise: the framework reverts, it does not refuse
        self.assertEqual(
            frappe.db.get_value("Salis Driver", doc.name, "national_id"),
            "1099887766",
            f"{FLEET_SUPERVISOR} changed a permlevel-1 field it holds no row for — the "
            "level is not being enforced on write",
        )

    def test_the_fleet_manager_can_create_a_driver_carrying_its_pii(self):
        """The sharper half of the same bug.

        On a create the reference document is `frappe.new_doc`, so an unwritable level-1
        field is BLANKED rather than restored (base_document.py:1276-1278). Before the
        write row existed, a Fleet Manager creating a driver got a record with no national
        ID, no driver ID and no licence number — and `driver_id` is the unique data-import
        key, so the loss is not cosmetic.
        """
        manager = self._user_with_role(FLEET_MANAGER)
        frappe.set_user(manager)
        created = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "S005 Created By Manager",
                "status": "Active",
                "project": self.project,
                "national_id": "1055443322",
                "driver_id": f"DRV{frappe.generate_hash(length=12)}",
                "phone": "0511111111",
                "license_number": "LIC-S005-CREATE",
            }
        ).insert()
        # No addCleanup: the row was inserted inside the test transaction, and FrappeTestCase
        # rolls rows back. Only non-row state (session user, Singles, files) needs a cleanup.

        stored = frappe.db.get_value(
            "Salis Driver", created.name, list(PII_FIELDS), as_dict=True
        )
        for field in sorted(PII_FIELDS):
            with self.subTest(field=field):
                self.assertTrue(
                    stored.get(field),
                    f"{field} was blanked on create — {FLEET_MANAGER} cannot write "
                    "permlevel 1",
                )
        self.assertEqual(stored.national_id, "1055443322")
        self.assertEqual(stored.license_number, "LIC-S005-CREATE")

    def test_the_pii_section_still_holds_the_four_fields_this_proves(self):
        """Non-vacuity for the behavioural methods above: if a field left permlevel 1 the
        proof would silently shrink to whatever remained."""
        shipped = json.loads(_DRIVER_JSON.read_text(encoding="utf-8"))
        elevated = {
            f["fieldname"] for f in shipped["fields"] if int(f.get("permlevel") or 0) == 1
        }
        self.assertEqual(
            elevated,
            PII_FIELDS,
            "the permlevel-1 field set on Salis Driver changed — re-derive this proof",
        )

    def test_only_the_two_reading_roles_gained_the_write(self):
        """The cost claim, read off the shipped JSON rather than trusted.

        A permlevel-1 row is not a duplicate of the permlevel-0 row for the same role —
        `is_perm_applicable` keeps only permlevel-0 rows (frappe/permissions.py:284) — so
        the pair (role, permlevel) is the identity, and deduplicating on role alone would
        strip exactly the field access this change depends on.
        """
        shipped = json.loads(_DRIVER_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]
        high = [p for p in rows if int(p.get("permlevel") or 0) == 1]
        self.assertEqual(
            {p["role"] for p in high},
            {FLEET_MANAGER, "System Manager"},
            "the permlevel-1 role set changed — this fix was supposed to add a flag to the "
            "two existing rows, not widen who reaches the PII",
        )
        for row in high:
            with self.subTest(role=row["role"]):
                self.assertEqual(row.get("read"), 1, f"{row['role']}: level-1 read missing")
                self.assertEqual(row.get("write"), 1, f"{row['role']}: level-1 write missing")

        # The explicit non-change: no level-0 authority moved.
        supervisor = [
            p
            for p in rows
            if p["role"] == FLEET_SUPERVISOR and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(supervisor), 1)
        self.assertEqual(
            supervisor[0].get("write"), 1, "Fleet Supervisor's level-0 write was collateral damage"
        )
        self.assertNotIn(
            FLEET_SUPERVISOR,
            {p["role"] for p in high},
            "Fleet Supervisor gained level-1 access it was never granted",
        )


# --- merged from test_salis_driver_portal_actions.py ---
APP_ROOT = Path(apex.__file__).resolve().parent
DRIVER_JS = Path(apex.__file__).resolve().parent / "salis" / "doctype" / "salis_driver" / "salis_driver.js"
TOKEN_DIR = APP_ROOT / "apex_core" / "doctype" / "masar_worker_token"
TOKEN_JS = TOKEN_DIR / "masar_worker_token.js"
TOKEN_PY = TOKEN_DIR / "masar_worker_token.py"
LINK_BUNDLE = APP_ROOT / "public" / "js" / "masar_worker_link.bundle.js"
TOKEN_MODULE = "apex.apex_core.doctype.masar_worker_token.masar_worker_token"
_ENDPOINT = re.compile(re.escape(TOKEN_MODULE) + r"\.([A-Za-z_][A-Za-z0-9_]*)")
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")
def _endpoints_called_from(path: Path) -> set[str]:
    """Names of token-module endpoints a client script routes a button to."""
    return set(_ENDPOINT.findall(_read(path)))
def _whitelisted_functions(path: Path) -> set[str]:
    """Module-level functions carrying any ``@frappe.whitelist(...)`` decorator."""
    tree = ast.parse(_read(path), filename=str(path))
    out = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            func = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "whitelist":
                out.add(node.name)
    return out
def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(_read(path), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined at module level in {path.name}")
def _call_names_in_order(func_node: ast.FunctionDef) -> list[str]:
    """Called names in source order — ``frappe.has_permission`` keeps its dotted form."""
    names = []
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.append((node.lineno, node.col_offset, func.id))
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            names.append((node.lineno, node.col_offset, f"{func.value.id}.{func.attr}"))
        elif isinstance(func, ast.Attribute):
            names.append((node.lineno, node.col_offset, func.attr))
    return [name for _line, _col, name in sorted(names)]
class TestSalisDriverPortalActions(unittest.TestCase):
    def test_driver_form_calls_only_the_driver_endpoints(self):
        """The driver form issues and revokes through the DRIVER endpoints only.

        The worker endpoint resolves its subject from an Employee id. Calling it
        from this form would either fail outright or, if a driver ever carried an
        employee link, mint the wrong audience's credential."""
        called = _endpoints_called_from(DRIVER_JS)
        self.assertEqual(called, {"issue_driver_link", "revoke_driver_link"})
        self.assertNotIn("issue_worker_link", _read(DRIVER_JS))

    def test_every_endpoint_the_desk_calls_is_whitelisted(self):
        """A button pointing at a non-whitelisted (or renamed) function is a dead
        surface that reviews pass and users find. Cross-checks the literal method
        paths in both client scripts against the controller's own decorators."""
        whitelisted = _whitelisted_functions(TOKEN_PY)
        self.assertIn("revoke_driver_link", whitelisted)
        called = _endpoints_called_from(DRIVER_JS) | _endpoints_called_from(TOKEN_JS)
        self.assertTrue(called, "endpoint scan found nothing — the regex is blind")
        self.assertEqual(called - whitelisted, set())

    def test_revocation_is_authorized_before_anything_is_disabled(self):
        """``revoke_driver_link`` must authorize BEFORE it revokes.

        Write permission on the token doctype is held by housing and HR roles too,
        so the doctype check alone would let an Accommodation Manager kill any
        driver's link. ``authorize_revocation`` is what narrows that to the fleet
        issuer roles and the caller's own project scope; ordering matters because a
        check after the write is not a check."""
        order = _call_names_in_order(_function(TOKEN_PY, "revoke_driver_link"))
        self.assertIn("frappe.has_permission", order)
        self.assertIn("authorize_revocation", order)
        self.assertIn("revoke_driver_tokens", order)
        self.assertLess(
            order.index("authorize_revocation"),
            order.index("revoke_driver_tokens"),
            "authorization must precede the revocation write",
        )

    def test_issuance_surface_never_parks_the_credential_in_the_browser(self):
        """The raw token is returned exactly once, to be shown and forgotten.

        A console line, a web-storage key or a cookie would each turn that one
        moment into a copy that outlives the driver's clearance, readable by anyone
        who later opens that browser profile."""
        for path in (DRIVER_JS, TOKEN_JS, LINK_BUNDLE):
            source = _read(path)
            for sink in ("console.", "localStorage", "sessionStorage", "document.cookie"):
                self.assertNotIn(sink, source, f"{path.name} writes the payload to {sink}")

    def test_token_record_routes_a_driver_row_to_the_driver_endpoint(self):
        """The token record's own action must branch on holder type.

        This is the bug the card names: a Driver-holder row has no ``employee``, so
        the single worker-only call site sent an undefined subject to the worker
        endpoint."""
        source = _read(TOKEN_JS)
        self.assertIn('frm.doc.holder_type === "Driver"', source)
        self.assertIn("frm.doc.driver", source)
        self.assertEqual(
            _endpoints_called_from(TOKEN_JS),
            {"issue_driver_link", "issue_worker_link"},
        )

    def test_both_audiences_keep_a_dialog_and_the_driver_form_uses_the_driver_one(self):
        """One dialog implementation, two named entry points.

        The worker entry point stays because Housing's arrival flow calls it by
        name; the driver form must call the driver one, which carries the
        no-password warning and the expiry."""
        bundle = _read(LINK_BUNDLE)
        for factory in ("show_portal_link_dialog", "show_worker_link_dialog", "show_driver_link_dialog"):
            self.assertIn(f"apex.masar.{factory} = function", bundle)
        self.assertIn("apex.masar.show_driver_link_dialog(", _read(DRIVER_JS))
        self.assertNotIn("show_worker_link_dialog", _read(DRIVER_JS))
if __name__ == "__main__":
    unittest.main()


# --- merged from test_salis_driver_state_contract.py ---
class TestSalisDriverStateContract(TestCase):
    def test_approved_current_hrms_leave_blocks_an_active_driver(self):
        driver = frappe._dict(
            full_name="Driver One",
            employee="EMP-1",
            status="Active",
        )
        fake_frappe = MagicMock()
        fake_frappe.db.get_value.side_effect = [driver, "Active"]
        fake_frappe.get_all.return_value = ["HR-LAP-1"]
        with (
            patch.object(utils, "frappe", fake_frappe),
            patch.object(utils, "_", side_effect=lambda message: message),
        ):
            reason = utils.rider_block_reason("DRV-1", "2026-08-14")

        self.assertIn("HR-LAP-1", reason)
        self.assertEqual(
            fake_frappe.get_all.call_args.kwargs["filters"],
            {
                "employee": "EMP-1",
                "status": "Approved",
                "docstatus": 1,
                "from_date": ["<=", frappe.utils.getdate("2026-08-14")],
                "to_date": [">=", frappe.utils.getdate("2026-08-14")],
            },
        )

    def test_cancelled_or_expired_leave_does_not_block_an_active_driver(self):
        driver = frappe._dict(
            full_name="Driver One",
            employee="EMP-1",
            status="Active",
        )
        fake_frappe = MagicMock()
        fake_frappe.db.get_value.side_effect = [driver, "Active"]
        fake_frappe.get_all.return_value = []
        with (
            patch.object(utils, "frappe", fake_frappe),
            patch.object(utils, "_", side_effect=lambda message: message),
        ):
            self.assertIsNone(utils.rider_block_reason("DRV-1", "2026-08-14"))

    def test_leave_query_failure_blocks_the_operation(self):
        with patch.object(
            utils.frappe,
            "get_all",
            side_effect=RuntimeError("database unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                utils._approved_leave_on("EMP-1", "2026-08-14")

    def test_driver_status_is_server_owned(self):
        new_doc = MagicMock(status="Released")
        new_doc.is_new.return_value = True
        salis_driver.SalisDriver._refuse_a_hand_written_status(new_doc)
        self.assertEqual(new_doc.status, "Active")

        existing = MagicMock()
        existing.is_new.return_value = False
        existing.has_value_changed.return_value = True
        fake_frappe = MagicMock()
        fake_frappe.PermissionError = frappe.PermissionError
        fake_frappe.throw.side_effect = lambda message, exc=None: (_ for _ in ()).throw(
            (exc or frappe.ValidationError)(message)
        )
        with (
            patch.object(salis_driver, "frappe", fake_frappe),
            patch.object(salis_driver, "_", side_effect=lambda message: message),
            self.assertRaises(frappe.PermissionError),
        ):
            salis_driver.SalisDriver._refuse_a_hand_written_status(existing)

    def test_driver_master_has_no_duplicate_leave_state(self):
        self.assertEqual(utils.BLOCKING_DRIVER_STATUSES, ("Stopped", "Released"))

        metadata = json.loads(
            Path(__file__).with_name("salis_driver.json").read_text(encoding="utf-8")
        )
        status = next(
            field for field in metadata["fields"] if field["fieldname"] == "status"
        )
        self.assertEqual(
            status["options"].splitlines(), ["Active", "Stopped", "Released"]
        )
        self.assertTrue(status["read_only"])
        self.assertNotIn("On Leave", {state["title"] for state in metadata["states"]})
