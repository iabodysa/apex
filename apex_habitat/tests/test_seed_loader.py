"""Guards for the data-driven seed loader (apex_habitat.tools.setup.seed).

The structural tests are pure (no site needed): they exercise ``load_specs``,
which has no ``frappe`` dependency. The parity test imports the legacy seeder to
prove the externalised JSON did not drift from the records it replaces.
"""

import json
import os
import tempfile
import unittest

from apex_habitat.tools.setup.seed import DATA_ROOT, SeedDataError, load_specs


class TestSeedLoaderStructure(unittest.TestCase):
    def test_habitat_email_template_spec_loads(self):
        specs = load_specs("habitat", only=["Email Template"])
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec["doctype"], "Email Template")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(len(spec["records"]), 3)
        # data files are co-located with the loader so __file__ resolution works
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
                json.dump({"doctype": "Email Template", "records": []}, fh)  # no 'key'
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


class TestSeedLoaderParity(unittest.TestCase):
    """The externalised JSON must match the legacy seeder it replaces."""

    def test_email_template_parity_with_legacy_seeder(self):
        from apex_habitat.habitat.email_templates_seed import _TEMPLATES

        spec = load_specs("habitat", only=["Email Template"])[0]
        by_name = {r["name"]: r for r in spec["records"]}
        self.assertEqual(set(by_name), {t["name"] for t in _TEMPLATES})
        for t in _TEMPLATES:
            self.assertEqual(by_name[t["name"]]["subject"], t["subject"])
            self.assertEqual(by_name[t["name"]]["response_html"], t["response_html"])
            self.assertEqual(by_name[t["name"]]["use_html"], 1)


if __name__ == "__main__":
    unittest.main()
