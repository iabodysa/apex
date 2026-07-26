# Copyright (c) 2026, AFMCO and contributors
"""Cross-writer guards for the two catalogues that have TWO install-time writers.

Maintenance Material is written by a module list (38 records) AND by a seed data
JSON (60 records); Safety Task Catalog by a function in ``apex/setup.py`` (10) AND
by a seed data JSON (51). Nothing checked the halves against each other, which is
how the default Maintenance Material Templates came to carry 13 child rows
pointing at materials only the JSON half supplied.

Three ways two writers of one catalogue can disagree, one test each:

1. both emit the same natural key with different content — whichever runs first
   wins and the other half is silently dropped, since every writer is create-only;
2. both emit the same UNIQUE field value under different keys — the second insert
   raises DuplicateEntryError mid-install;
3. their union no longer covers a key some other seeded record links to — the
   template's child Link dangles and Frappe refuses the whole template.

Pure: reads the JSON off disk and the writers' module-level constants by AST, so
no site and no ``frappe`` import is needed. The ``apex/setup.py`` writer is read by
AST precisely because importing it would pull in ``frappe``.
"""

import ast
import json
import os
import unittest

from apex.apex_core.setup.seed import load_specs

_HERE = os.path.abspath(__file__)
# Repo root: .../apex_core/setup/<this file> -> up four to the directory holding apex/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))


def _module_constant(relpath, name):
    """The literal value of a module-level assignment, without importing the module."""
    with open(os.path.join(_REPO_ROOT, relpath), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{relpath} no longer defines {name}")


def _local_constant(relpath, func, name):
    """The literal value of an assignment inside one function body."""
    with open(os.path.join(_REPO_ROOT, relpath), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                    getattr(t, "id", None) == name for t in stmt.targets
                ):
                    return ast.literal_eval(stmt.value)
    raise AssertionError(f"{relpath}:{func} no longer defines {name}")


def _json_records(relpath):
    with open(os.path.join(_REPO_ROOT, relpath), encoding="utf-8") as fh:
        return json.load(fh)["records"]


def _material_writers():
    """The two writers of Maintenance Material, as {writer label: [records]}."""
    return {
        "maintenance_material_catalog.MAINTENANCE_MATERIAL_CATALOG": _module_constant(
            "apex/habitat/doctype/maintenance_material/maintenance_material_catalog.py",
            "MAINTENANCE_MATERIAL_CATALOG",
        ),
        "data/habitat/maintenance_material.json": _json_records(
            "apex/apex_core/setup/data/habitat/maintenance_material.json"
        ),
    }


def _safety_task_writers():
    """The two writers of Safety Task Catalog, as {writer label: [records]}."""
    return {
        "setup.create_safety_task_catalogs": _local_constant(
            "apex/setup.py", "create_safety_task_catalogs", "tasks"
        ),
        "data/habitat/safety_task_catalog.json": _json_records(
            "apex/apex_core/setup/data/habitat/safety_task_catalog.json"
        ),
    }


def _conflicting_keys(writers, key):
    """Keys emitted by more than one writer with differing content.

    Returns ``[(key, writer_a, writer_b, differing_field)]``. A key emitted twice
    with IDENTICAL content is redundant but harmless, so it is not a conflict.
    """
    seen = {}
    conflicts = []
    for label, records in writers.items():
        for record in records:
            previous_label, previous = seen.setdefault(record[key], (label, record))
            if previous_label == label:
                continue
            for field in sorted(set(previous) | set(record)):
                if previous.get(field) != record.get(field):
                    conflicts.append((record[key], previous_label, label, field))
                    break
    return conflicts


def _cross_writer_duplicates(writers, key, unique_field):
    """Values of a UNIQUE field emitted by two writers under DIFFERENT natural keys."""
    seen = {}
    clashes = []
    for label, records in writers.items():
        for record in records:
            value = record.get(unique_field)
            if value is None:
                continue
            previous_label, previous_key = seen.setdefault(value, (label, record[key]))
            if previous_label != label and previous_key != record[key]:
                clashes.append((unique_field, value, previous_label, previous_key,
                                label, record[key]))
    return clashes


class TestMaintenanceMaterialWriters(unittest.TestCase):
    KEY = "material_name"

    def test_writers_do_not_conflict(self):
        conflicts = _conflicting_keys(_material_writers(), self.KEY)
        self.assertEqual(
            conflicts, [],
            "Maintenance Material writers disagree (key, writer A, writer B, field): "
            f"{conflicts}",
        )

    def test_writers_cover_every_seeded_template_child_link(self):
        """Every ``items[].material`` a default template links to must be supplied.

        Both halves of the template seed are checked — the module constant the
        seeder inserts and the externalised JSON the loader applies — because a
        rename in either material writer breaks whichever of the two still
        names the old value.
        """
        writers = _material_writers()
        supplied = {r[self.KEY] for records in writers.values() for r in records}

        templates = {
            "maintenance_material_template_seed.TEMPLATE_SEEDS": _module_constant(
                "apex/apex_core/setup/seeders/maintenance_material_template_seed.py",
                "TEMPLATE_SEEDS",
            ),
            "data/habitat/maintenance_material_template.json": _json_records(
                "apex/apex_core/setup/data/habitat/maintenance_material_template.json"
            ),
        }
        dangling = sorted(
            {
                (source, tpl["template_name"], row["material"])
                for source, records in templates.items()
                for tpl in records
                for row in tpl.get("items") or []
                if row.get("material") not in supplied
            }
        )
        self.assertEqual(
            dangling, [],
            "Maintenance Material Template child rows link to materials no writer "
            f"supplies (source, template, material): {dangling}. Writers consulted: "
            f"{sorted(writers)}",
        )

    def test_externalised_json_is_still_the_larger_writer(self):
        """The JSON half is the declared source of truth, so it must not shrink to a
        stub while the module list quietly becomes the real catalogue."""
        writers = _material_writers()
        self.assertGreater(
            len(writers["data/habitat/maintenance_material.json"]),
            0,
            "maintenance_material.json must not be emptied",
        )


class TestSafetyTaskCatalogWriters(unittest.TestCase):
    KEY = "task_code"

    def test_writers_do_not_conflict(self):
        conflicts = _conflicting_keys(_safety_task_writers(), self.KEY)
        self.assertEqual(
            conflicts, [],
            "Safety Task Catalog writers disagree (task_code, writer A, writer B, "
            f"field): {conflicts}",
        )

    def test_writers_do_not_clash_on_the_unique_title(self):
        """Two writers emitting one task under two codes duplicates the master."""
        clashes = _cross_writer_duplicates(_safety_task_writers(), self.KEY, "task_title")
        self.assertEqual(
            clashes, [],
            f"Safety Task Catalog writers emit the same task under two codes: {clashes}",
        )


class TestCrossWriterDetectors(unittest.TestCase):
    """The detectors above must be able to FAIL, asserted on planted inputs."""

    def test_conflict_detector_names_the_key_and_both_writers(self):
        writers = {
            "a": [{"material_name": "LED Bulbs", "material_category": "Electrical"}],
            "b": [{"material_name": "LED Bulbs", "material_category": "General"}],
        }
        self.assertEqual(
            _conflicting_keys(writers, "material_name"),
            [("LED Bulbs", "a", "b", "material_category")],
        )

    def test_conflict_detector_allows_an_identical_repeat(self):
        record = {"material_name": "LED Bulbs", "material_category": "Electrical"}
        self.assertEqual(
            _conflicting_keys({"a": [dict(record)], "b": [dict(record)]}, "material_name"),
            [],
        )

    def test_unique_clash_detector_ignores_a_repeat_under_the_same_key(self):
        writers = {
            "a": [{"task_code": "SAF-001", "task_title": "Sweep"}],
            "b": [{"task_code": "SAF-001", "task_title": "Sweep"}],
        }
        self.assertEqual(_cross_writer_duplicates(writers, "task_code", "task_title"), [])

    def test_unique_clash_detector_flags_two_codes_for_one_title(self):
        writers = {
            "a": [{"task_code": "SAF-001", "task_title": "Sweep"}],
            "b": [{"task_code": "HH-301", "task_title": "Sweep"}],
        }
        self.assertEqual(
            _cross_writer_duplicates(writers, "task_code", "task_title"),
            [("task_title", "Sweep", "a", "SAF-001", "b", "HH-301")],
        )

    def test_writer_readers_agree_with_the_loader(self):
        """The JSON half is read here off disk; it must be the same set the seed loader
        will apply, or this guard would be watching a file nobody seeds."""
        spec = load_specs("habitat", only=["Maintenance Material"])[0]
        self.assertEqual(
            spec["records"],
            _material_writers()["data/habitat/maintenance_material.json"],
        )


if __name__ == "__main__":
    unittest.main()
