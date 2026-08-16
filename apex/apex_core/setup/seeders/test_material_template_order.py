# Copyright (c) 2026, AFMCO and contributors
"""Order guard: no Maintenance Material Template may be built before its materials.

The template child rows are REQUIRED Links onto Maintenance Material, and the
catalogue has two writers. When ``seed_templates`` ran before the data-JSON writer,
four of the eight default templates named materials that did not exist yet.

This asserts the ORDER of the calls the seeder makes, not the call site that
happens to invoke it, so the templates stay safe wherever ``after_install`` places
them. Site-free: the seeder's ``frappe`` and both material writers are replaced by
recorders, so the sequence is observed at the call boundary.
"""

import unittest
from unittest.mock import patch

from apex.apex_core.setup.seeders import maintenance_material_template_seed as seeder

_CATALOGUE_WRITER = "catalogue-module"
_DATA_WRITER = "data-json"


class _RecordingDoc:
    def __init__(self, payload, log):
        self._payload = payload
        self._log = log

    def insert(self, **_kwargs):
        self._log.append(("template", self._payload["template_name"]))


class _RecordingDB:
    def exists(self, _doctype, _key):
        return False

    def commit(self):
        return None


class _RecordingFrappe:
    def __init__(self, log):
        self.db = _RecordingDB()
        self._log = log

    def get_doc(self, payload):
        return _RecordingDoc(payload, self._log)


def _run_seed_templates():
    """Run ``seed_templates`` with every writer replaced by a recorder.

    Returns the ordered event log and the arguments the data writer was given.
    """
    log = []
    data_calls = []

    def _record_catalogue():
        log.append((_CATALOGUE_WRITER, None))

    def _record_data(module_dir, only=None):
        log.append((_DATA_WRITER, module_dir))
        data_calls.append((module_dir, tuple(only or ())))

    with patch.object(seeder, "frappe", _RecordingFrappe(log)), \
            patch.object(seeder, "seed_catalog", _record_catalogue), \
            patch.object(seeder, "seed", _record_data):
        seeder.seed_templates()
    return log, data_calls


class TestMaterialsAreSeededBeforeTemplates(unittest.TestCase):
    def test_both_material_writers_run_before_the_first_template(self):
        log, _ = _run_seed_templates()
        kinds = [event[0] for event in log]
        self.assertIn(_CATALOGUE_WRITER, kinds, "the catalogue module writer never ran")
        self.assertIn(_DATA_WRITER, kinds, "the seed-data writer never ran")
        first_template = kinds.index("template")
        self.assertLess(
            kinds.index(_CATALOGUE_WRITER), first_template,
            f"a template is built before the catalogue writer runs: {kinds}",
        )
        self.assertLess(
            kinds.index(_DATA_WRITER), first_template,
            f"a template is built before the seed-data writer runs: {kinds}",
        )

    def test_the_data_writer_is_asked_for_the_material_doctype(self):
        _, data_calls = _run_seed_templates()
        self.assertEqual(data_calls, [("habitat", ("Maintenance Material",))])

    def test_every_default_template_is_still_built(self):
        log, _ = _run_seed_templates()
        built = [name for kind, name in log if kind == "template"]
        self.assertEqual(built, [tpl["template_name"] for tpl in seeder.TEMPLATE_SEEDS])

    def test_seed_materials_is_not_a_no_op(self):
        """The regression this guard exists for: ``seed_materials`` was reduced to an
        empty stub, which silently moved the material seed AFTER the templates."""
        log = []
        with patch.object(seeder, "seed_catalog", lambda: log.append(_CATALOGUE_WRITER)), \
                patch.object(seeder, "seed", lambda *a, **k: log.append(_DATA_WRITER)):
            seeder.seed_materials()
        self.assertEqual(log, [_CATALOGUE_WRITER, _DATA_WRITER])


if __name__ == "__main__":
    unittest.main()
