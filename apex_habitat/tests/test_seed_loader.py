# Copyright (c) 2026, AFMCO and contributors
"""Guards for the data-driven seed loader (apex_habitat.apex_core.setup.seed).

The structural tests are pure (no site needed): they exercise ``load_specs``,
which has no ``frappe`` dependency. (The legacy-seeder parity test was dropped in
the seed consolidation (M-10/M-11) when the seeders it compared against were
retired; the JSON shape is now guarded by tests/test_seed_parity_*.)
"""

import json
import os
import tempfile
import unittest

from apex_habitat.apex_core.setup.seed import DATA_ROOT, SeedDataError, load_specs


class TestSeedLoaderStructure(unittest.TestCase):
    def test_habitat_email_template_spec_loads(self):
        specs = load_specs("habitat", only=["Email Template"])
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec["doctype"], "Email Template")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(len(spec["records"]), 3)
        # [#cvogqp]
        self.assertTrue(os.path.isdir(os.path.join(DATA_ROOT, "habitat")))

    def test_only_filter_excludes_other_doctypes(self):
        self.assertEqual(load_specs("habitat", only=["No Such DocType"]), [])

    def test_missing_module_dir_returns_empty(self):
        self.assertEqual(load_specs("does_not_exist"), [])

    def test_missing_required_key_raises(self):
        with tempfile.TemporaryDirectory() as root:
            mod = os.path.join(root, "habitat")
            os.makedirs(mod)
            with open(os.path.join(mod, "bad.json"), "w", encoding="utf-8") as fh:
                json.dump({"doctype": "Email Template", "records": []}, fh)  # [#5skuyx]
            with self.assertRaises(SeedDataError):
                load_specs("habitat", data_root=root)

    def test_records_must_be_a_list(self):
        with tempfile.TemporaryDirectory() as root:
            mod = os.path.join(root, "habitat")
            os.makedirs(mod)
            with open(os.path.join(mod, "bad.json"), "w", encoding="utf-8") as fh:
                json.dump({"doctype": "X", "key": "name", "records": {}}, fh)
            with self.assertRaises(SeedDataError):
                load_specs("habitat", data_root=root)


if __name__ == "__main__":
    unittest.main()
