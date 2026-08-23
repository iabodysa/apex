# Copyright (c) 2026, afmcoltd

"""A DocType a user opens must reach what hangs off it without a search.

``links`` in a customisation file is synced by ``sync_customizations_for_doctype``
(frappe/modules/utils.py:157-174): the "DocType Link" branch looks up each row by
(parent, link_doctype, link_fieldname) and calls ``db_update`` when found, ``db_insert``
only when absent — it is never deleted, so a row an operator adds through the desk
Connections editor survives every migrate. This is why the same file may also carry
``custom_perms`` (frappe/modules/utils.py:183-188, deleted and reinserted whole on every
migrate) and the two must not be read as one mechanism.

Every test below is derived, not hand-counted: it re-scans every DocType JSON the app
ships for a genuine ``fieldtype: "Link"`` field whose ``options`` names the customised
DocType, resolves a child-table field to the parent that embeds it, and compares that
derived set against the ``links`` array on disk. A new inbound Link field that nobody
wires into a Connections entry fails this test, and a stale entry pointing at a field
that no longer exists fails it too.
"""

import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))

CUSTOM_JSON_FILES = (
    APP_ROOT / "apex_core" / "custom" / "employee_advance.json",
    APP_ROOT / "habitat" / "custom" / "address.json",
    APP_ROOT / "habitat" / "custom" / "cost_center.json",
    APP_ROOT / "habitat" / "custom" / "employee.json",
    APP_ROOT / "habitat" / "custom" / "project.json",
    APP_ROOT / "salis" / "custom" / "issue.json",
)

LINKED_DOCTYPE_BY_FILE = {
    APP_ROOT / "apex_core" / "custom" / "employee_advance.json": "Employee Advance",
    APP_ROOT / "habitat" / "custom" / "address.json": "Address",
    APP_ROOT / "habitat" / "custom" / "cost_center.json": "Cost Center",
    APP_ROOT / "habitat" / "custom" / "employee.json": "Employee",
    APP_ROOT / "habitat" / "custom" / "project.json": "Project",
    APP_ROOT / "salis" / "custom" / "issue.json": "Issue",
}


def _doctype_jsons():
    """One (name, declaration) pair per DocType JSON the app ships, skipping test fixtures."""
    found = {}
    for path in APP_ROOT.rglob("doctype/*/*.json"):
        if path.stem != path.parent.name:
            continue
        data = json.loads(path.read_text())
        name = data.get("name")
        if name:
            found[name] = data
    return found


def _child_table_parents(doctypes):
    """Map a child DocType name to every (parent, table_fieldname) that embeds it."""
    parents = {}
    for name, data in doctypes.items():
        for field in data.get("fields", []):
            if field.get("fieldtype") in ("Table", "Table MultiSelect"):
                parents.setdefault(field["options"], []).append((name, field["fieldname"]))
    return parents


def _expected_links(target, doctypes, child_parents):
    """Every genuine inbound Link field to ``target``, as the tuple a links entry declares."""
    expected = set()
    for name, data in doctypes.items():
        if data.get("issingle"):
            continue
        for field in data.get("fields", []):
            if field.get("fieldtype") != "Link" or field.get("options") != target:
                continue
            if data.get("istable"):
                parents = child_parents.get(name, [])
                assert parents, f"{name} embeds nowhere; cannot link {target} through it"
                for parent, table_fieldname in parents:
                    expected.add((name, field["fieldname"], parent, table_fieldname))
            else:
                expected.add((name, field["fieldname"], None, None))
    return expected


def _declared_links(path):
    """Every links entry on disk, as the same tuple shape ``_expected_links`` returns."""
    data = json.loads(path.read_text())
    declared = set()
    for entry in data.get("links", []):
        declared.add(
            (
                entry["link_doctype"],
                entry["link_fieldname"],
                entry.get("parent_doctype"),
                entry.get("table_fieldname"),
            )
        )
    return declared


class TestCustomJsonCarriesNoCustomPerms(FrappeTestCase):
    """``custom_perms`` is deleted and reinserted whole every migrate; Custom DocPerm is
    seeded instead by ``app_owned_permissions_seed.seed_app_owned_permissions``."""

    def test_no_apex_customisation_file_carries_custom_perms(self):
        for path in CUSTOM_JSON_FILES:
            with self.subTest(file=path.name):
                data = json.loads(path.read_text())
                self.assertNotIn("custom_perms", data)


class TestDocTypeLinksMatchTheFieldsThatActuallyPointHere(FrappeTestCase):
    """A links entry with no backing field, or a backing field with no links entry,
    both leave a DocType a user opened unable to reach records that hang off it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doctypes = _doctype_jsons()
        cls.child_parents = _child_table_parents(cls.doctypes)

    def test_every_customisation_file_carries_exactly_its_derived_links(self):
        for path, target in LINKED_DOCTYPE_BY_FILE.items():
            with self.subTest(file=path.name, doctype=target):
                expected = _expected_links(target, self.doctypes, self.child_parents)
                declared = _declared_links(path)
                self.assertEqual(expected, declared)
