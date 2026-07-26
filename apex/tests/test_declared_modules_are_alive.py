# Copyright (c) 2026, AFMCO and contributors
"""Guard: no name in modules.txt is a ghost — a module that owns nothing at all.

A module line costs more than a line. ``frappe.installer.add_module_defs``
(installer.py:686-692) inserts one ``Module Def`` per entry of
``frappe.get_module_list(app)`` on every ``install-app``, and
``frappe.config.get_modules_from_all_apps`` lists modules straight off those rows.
So a declared name is published to the Desk module list, the User "Block Modules"
picker, the Module Profile picker and every module-count claim on EVERY fresh
site — whether or not anything is behind it.

That is exactly what the SIM Operations fold left behind (A-187): the source moved
to ``apex/logistay/``, every record was restamped, the package was emptied down to
``__init__.py`` — and the modules.txt line stayed, so the ghost kept being minted.
It had already produced one published-docs error ("the four names in modules.txt"
when the file declared five). The fold patch drops the row, but a site installed
fresh logs that patch complete-without-running (installer.py:324-325), so nothing
in the repo could tell that the ghost was still shipping.

A declared module is ALIVE if either half of a Frappe module exists:

  * RECORDS — some shipped JSON under ``apex/`` declares ``"module": <name>``
    (DocType, Report, Page, Workspace, Notification, Dashboard Chart, Number Card,
    Web Form, Print Format, ...); or
  * CODE — its package ``apex/<scrub(name)>/`` holds anything but ``__init__.py``.

Only NEITHER fails. A brand-new module that ships code but has not earned its first
record yet passes on the code half, and a records-only module that ships no Python
passes on the records half — both are real, loadable modules. There is deliberately
no escape-hatch marker for "reserved name, empty by design": reserving a name in
modules.txt is not free, it publishes a ghost to every new site, and a name costs
nothing to add on the day the first record or file lands.

Central by necessity (A-196): the invariant is over ``apex/modules.txt`` — a
root-level register — and over EVERY module's records and package at once, so no
single module directory is an honest home. Same shape as the patches.txt guard
beside it. It shipped at ``apex/test_declared_modules_are_alive.py`` where frappe
collects zero tests from it (see test_colocation_ratchet.py's app-root clause).

Pure stdlib — no live site needed.
Run standalone (from the repo root):
  python3 -m unittest apex.tests.test_declared_modules_are_alive -v
"""

import glob
import json
import os
import unittest

# This module lives under apex/tests/, so the app root is one level up.
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_TXT = os.path.join(APP_ROOT, "modules.txt")


def _scrub(name):
    """Mirror of frappe.scrub (frappe/__init__.py:1463) — module name to folder."""
    return name.replace(" ", "_").replace("-", "_").lower()


def _declared_modules():
    """modules.txt entries, in file order, read as frappe.get_file_items reads them:
    stripped, blank lines dropped, ``#`` lines dropped."""
    with open(MODULES_TXT, encoding="utf-8") as fh:
        lines = [line.strip() for line in fh]
    return [line for line in lines if line and not line.startswith("#")]


def _records_by_module(app_root=APP_ROOT):
    """{module name: [rel path, ...]} over every shipped JSON declaring a module."""
    found = {}
    for path in sorted(glob.glob(os.path.join(app_root, "**", "*.json"), recursive=True)):
        if "node_modules" in path:
            continue
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        if isinstance(data, dict) and isinstance(data.get("module"), str):
            found.setdefault(data["module"], []).append(os.path.relpath(path, app_root))
    return found


def _package_contents(modules, app_root=APP_ROOT):
    """{module name: [rel path, ...] | None} — files in the module package other than
    ``__init__.py``. None means the package folder itself is missing."""
    found = {}
    for module in modules:
        package = os.path.join(app_root, _scrub(module))
        if not os.path.isdir(package):
            found[module] = None
            continue
        contents = []
        for path in sorted(glob.glob(os.path.join(package, "**", "*"), recursive=True)):
            if os.path.isdir(path) or "__pycache__" in path:
                continue
            if os.path.relpath(path, package) == "__init__.py":
                continue
            contents.append(os.path.relpath(path, app_root))
        found[module] = contents
    return found


def _ghost_modules(declared, records_by_module, package_contents):
    """Declared modules owning no record AND no code. Pure over its inputs so the
    planted-ghost and legitimate-lookalike cases below are provable without touching
    the working tree."""
    offenders = []
    for module in declared:
        if records_by_module.get(module):
            continue
        contents = package_contents.get(module)
        if contents:
            continue
        reason = (
            f"apex/{_scrub(module)}/ does not exist"
            if contents is None
            else f"apex/{_scrub(module)}/ holds nothing but __init__.py"
        )
        offenders.append(f"{module!r}: no shipped JSON declares it, and {reason}")
    return offenders


class TestDeclaredModulesAreAlive(unittest.TestCase):
    def test_the_registry_read_is_non_vacuous(self):
        declared = _declared_modules()
        self.assertIn("Habitat", declared, "modules.txt read found no Habitat — parser broke")

    def test_the_record_scan_is_non_vacuous(self):
        """An empty scan would make every module look like a ghost, or — paired with
        the package scan — make the guard pass for entirely the wrong reason."""
        records = _records_by_module()
        self.assertIn("Habitat", records)
        self.assertGreater(len(records["Habitat"]), 1)

    def test_the_package_scan_is_non_vacuous(self):
        contents = _package_contents(["Habitat", "Apex Core"])
        self.assertTrue(contents["Habitat"], "Habitat package scanned as empty — scan broke")
        self.assertTrue(contents["Apex Core"], "scrub() folder mapping broke")

    def test_no_declared_module_is_a_ghost(self):
        declared = _declared_modules()
        offenders = _ghost_modules(declared, _records_by_module(), _package_contents(declared))
        self.assertEqual(
            offenders,
            [],
            "modules.txt declares a module that owns no record and no code. Frappe still "
            "mints a Module Def for it on every fresh install, so it shows up in the Desk "
            "module list and in every module count while routing nothing. Drop the line "
            "(and register a patch deleting the Module Def on existing sites), or ship the "
            "record or file that makes it real:\n" + "\n".join(f"  {o}" for o in offenders),
        )

    def test_detector_flags_a_planted_ghost(self):
        """The failure this guard exists for, proved without editing the tree."""
        offenders = _ghost_modules(
            ["Habitat", "Ghost Module"],
            {"Habitat": ["habitat/doctype/building/building.json"]},
            {"Habitat": ["habitat/api.py"], "Ghost Module": []},
        )
        self.assertEqual(len(offenders), 1)
        self.assertIn("Ghost Module", offenders[0])
        self.assertIn("apex/ghost_module/", offenders[0])

    def test_detector_flags_a_declared_module_with_no_package_at_all(self):
        offenders = _ghost_modules(["Nowhere"], {}, {"Nowhere": None})
        self.assertIn("does not exist", offenders[0])

    def test_detector_accepts_a_code_only_module(self):
        """A genuinely new module that ships code before its first record is alive —
        Frappe loads it, and its dotted paths resolve."""
        self.assertEqual(_ghost_modules(["Fresh"], {}, {"Fresh": ["fresh/tasks/sweep.py"]}), [])

    def test_detector_accepts_a_records_only_module(self):
        """The mirror shape: a module whose surface is entirely is_standard JSON."""
        offenders = _ghost_modules(
            ["Paperwork"], {"Paperwork": ["paperwork/report/x/x.json"]}, {"Paperwork": []}
        )
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
