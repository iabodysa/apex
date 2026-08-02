# Copyright (c) 2026, AFMCO and contributors
"""Regression coverage for defaults required by a fresh Apex installation."""

import inspect
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.nestedset import NestedSetMultipleRootsError, get_descendants_of, rebuild_tree

from apex import hooks, setup
from apex.apex_core.setup import setup_wizard
from apex.patches.v1_x import seed_accommodation_item_groups


class TestFreshInstallDefaults(FrappeTestCase):
    def _item_record(self):
        suffix = frappe.generate_hash(length=12).upper()
        return {
            "doctype": "Item",
            "item_code": f"ACC-TEST-{suffix}",
            "item_name": f"Apex Test Item {suffix}",
            "item_group": "Accommodation Bedding",
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "description": "Shipped description",
        }

    def test_early_install_explicitly_defers_until_erpnext_creates_root(self):
        with (
            patch.object(setup, "_get_item_group_root", side_effect=[None, "ERPNext Root"]),
            patch.object(setup, "create_accommodation_item_groups") as create_groups,
            patch.object(setup, "create_accommodation_items") as create_items,
        ):
            self.assertFalse(setup.create_accommodation_item_defaults(allow_deferred=True))
            self.assertTrue(setup.create_accommodation_item_defaults())

        create_groups.assert_called_once_with("ERPNext Root")
        create_items.assert_called_once_with()
        self.assertNotIn("make_records", inspect.getsource(setup))

    def test_required_paths_fail_when_erpnext_root_is_missing(self):
        with patch.object(setup, "_get_item_group_root", return_value=None):
            with self.assertRaises(frappe.DoesNotExistError):
                setup.create_accommodation_item_defaults()

            with (
                patch.object(setup_wizard, "apply_apex_setup"),
                self.assertRaises(frappe.DoesNotExistError),
            ):
                setup_wizard.setup_wizard_complete({})

            with self.assertRaises(frappe.DoesNotExistError):
                seed_accommodation_item_groups.execute()

    def test_root_lookup_is_language_independent_and_rejects_duplicates(self):
        with patch.object(setup.frappe, "get_all", return_value=["Translated Item Group Root"]):
            self.assertEqual(setup._get_item_group_root(), "Translated Item Group Root")

        with patch.object(setup.frappe, "get_all", return_value=["Root A", "Root B"]):
            with self.assertRaises(NestedSetMultipleRootsError):
                setup._get_item_group_root()

    def test_item_group_seeder_is_idempotent_and_preserves_containment(self):
        root = setup._get_item_group_root()
        self.assertIsNotNone(root)

        suffix = frappe.generate_hash(length=12)
        groups = [f"Apex Fresh Install Group {suffix}"]
        with patch.object(setup, "ACCOMMODATION_ITEM_GROUPS", groups):
            setup.create_accommodation_item_groups(root)
            setup.create_accommodation_item_groups(root)

        self.assertEqual(frappe.db.count("Item Group", {"name": groups[0]}), 1)
        self.assertIn(
            groups[0],
            get_descendants_of("Item Group", root, ignore_permissions=True),
        )

    def test_item_group_seeder_rebuilds_invalid_root_before_inserting(self):
        root = setup._get_item_group_root()
        self.assertIsNotNone(root)
        group = f"Apex Invalid Root Recovery {frappe.generate_hash(length=12)}"
        root_lft = frappe.db.get_value("Item Group", root, "lft")

        try:
            frappe.db.set_value(
                "Item Group",
                root,
                "rgt",
                root_lft,
                update_modified=False,
            )
            with (
                patch.object(setup, "ACCOMMODATION_ITEM_GROUPS", [group]),
                patch.object(setup, "rebuild_tree", wraps=rebuild_tree) as rebuild,
            ):
                setup.create_accommodation_item_groups(root)

            rebuild.assert_called_once_with("Item Group", "parent_item_group")
            self.assertEqual(
                frappe.db.get_value("Item Group", group, "parent_item_group"),
                root,
            )
            self.assertIn(
                group,
                get_descendants_of("Item Group", root, ignore_permissions=True),
            )
        finally:
            if frappe.db.exists("Item Group", group):
                frappe.delete_doc("Item Group", group, ignore_permissions=True)
            rebuild_tree("Item Group", "parent_item_group")

    def test_item_group_seeder_repairs_parent_that_is_not_a_group(self):
        root = setup._get_item_group_root()
        self.assertIsNotNone(root)
        suffix = frappe.generate_hash(length=12)
        invalid_parent = f"Apex Invalid Parent {suffix}"
        group = f"Apex Parent Recovery {suffix}"
        for name in (invalid_parent, group):
            frappe.get_doc(
                {
                    "doctype": "Item Group",
                    "item_group_name": name,
                    "parent_item_group": root,
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Item Group",
            group,
            "parent_item_group",
            invalid_parent,
            update_modified=False,
        )

        try:
            with patch.object(setup, "ACCOMMODATION_ITEM_GROUPS", [group]):
                setup.create_accommodation_item_groups(root)

            self.assertEqual(
                frappe.db.get_value("Item Group", group, "parent_item_group"),
                root,
            )
        finally:
            for name in (group, invalid_parent):
                if frappe.db.exists("Item Group", name):
                    frappe.delete_doc("Item Group", name, ignore_permissions=True)
            rebuild_tree("Item Group", "parent_item_group")

    def test_items_are_deferred_outside_fixture_sync(self):
        fixture_path = Path(setup.frappe.get_app_path("apex", "fixtures", "item.json"))
        data_path = Path(
            setup.frappe.get_app_path(
                "apex",
                "apex_core",
                "setup",
                "accommodation_items.json",
            )
        )

        self.assertFalse(fixture_path.exists())
        self.assertTrue(data_path.exists())
        self.assertNotIn('"dt": "Item"', inspect.getsource(hooks))

    def test_item_seeder_inserts_missing_resource_record(self):
        record = self._item_record()
        with patch.object(setup, "_load_accommodation_item_records", return_value=[record]):
            setup.create_accommodation_items()

        item = frappe.get_doc("Item", record["item_code"])
        self.assertEqual(item.item_group, record["item_group"])
        self.assertEqual(item.description, record["description"])

    def test_item_seeder_is_idempotent(self):
        record = self._item_record()
        with patch.object(setup, "_load_accommodation_item_records", return_value=[record]):
            setup.create_accommodation_items()
            setup.create_accommodation_items()

        self.assertEqual(frappe.db.count("Item", {"item_code": record["item_code"]}), 1)

    def test_item_seeder_preserves_existing_customization(self):
        record = self._item_record()
        with patch.object(setup, "_load_accommodation_item_records", return_value=[record]):
            setup.create_accommodation_items()
            frappe.db.set_value("Item", record["item_code"], "description", "Customized locally")
            setup.create_accommodation_items()

        self.assertEqual(
            frappe.db.get_value("Item", record["item_code"], "description"),
            "Customized locally",
        )

    def test_custody_article_seeder_is_idempotent(self):
        """Custody Article autonames by naming_series, so the old guard — a probe on
        frappe.db.exists("Custody Article", <article_name>) — could never match a
        CART-#### name and every after_install re-inserted all ten. The guard is keyed
        on the article_name FIELD, like create_safety_task_catalogs. Runs the seeder
        twice in one process and counts rows, because a single run always passes."""
        frappe.db.delete("Custody Article")

        setup.create_custody_articles()
        first = sorted(frappe.get_all("Custody Article", pluck="article_name"))
        setup.create_custody_articles()
        second = sorted(frappe.get_all("Custody Article", pluck="article_name"))

        self.assertEqual(len(first), 10)
        self.assertEqual(second, first, "the second run re-inserted the whole catalogue")

    def test_after_migrate_recovery_is_hooked_and_defers_without_root(self):
        self.assertIn("apex.setup.after_migrate", hooks.after_migrate)
        with patch.object(setup, "_get_item_group_root", return_value=None):
            self.assertFalse(setup.after_migrate())

    def test_after_migrate_preserves_customized_default_group_parent(self):
        root = setup._get_item_group_root()
        self.assertIsNotNone(root)
        setup.create_accommodation_item_groups(root)

        custom_parent = f"Apex Custom Item Hierarchy {frappe.generate_hash(length=12)}"
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": custom_parent,
                "parent_item_group": root,
                "is_group": 1,
            }
        ).insert(ignore_permissions=True)

        default_group = frappe.get_doc("Item Group", setup.ACCOMMODATION_ITEM_GROUPS[0])
        default_group.parent_item_group = custom_parent
        default_group.save(ignore_permissions=True)
        rebuild_tree("Item Group", "parent_item_group")

        try:
            setup.after_migrate()
            self.assertEqual(
                frappe.db.get_value(
                    "Item Group",
                    default_group.name,
                    "parent_item_group",
                ),
                custom_parent,
            )
        finally:
            default_group.reload()
            default_group.parent_item_group = root
            default_group.save(ignore_permissions=True)
            frappe.delete_doc("Item Group", custom_parent, ignore_permissions=True)
            rebuild_tree("Item Group", "parent_item_group")

    def test_after_migrate_does_not_rebuild_or_write_valid_item_group_tree(self):
        root = setup._get_item_group_root()
        self.assertIsNotNone(root)
        setup.create_accommodation_item_defaults()

        root_lft, root_rgt = frappe.db.get_value(
            "Item Group",
            root,
            ["lft", "rgt"],
        )
        self.assertLess(root_lft, root_rgt)
        for group in setup.ACCOMMODATION_ITEM_GROUPS:
            parent = frappe.db.get_value("Item Group", group, "parent_item_group")
            self.assertTrue(frappe.db.get_value("Item Group", parent, "is_group"))

        with (
            patch.object(setup, "rebuild_tree") as rebuild,
            patch.object(setup.frappe, "get_doc", wraps=setup.frappe.get_doc) as get_doc,
        ):
            setup.after_migrate()

        rebuild.assert_not_called()
        item_group_documents = [
            call
            for call in get_doc.call_args_list
            if call.args
            and (
                call.args[0] == "Item Group"
                or (
                    isinstance(call.args[0], dict)
                    and call.args[0].get("doctype") == "Item Group"
                )
            )
        ]
        self.assertEqual(item_group_documents, [])

    def test_install_and_setup_wizard_use_permanent_seeder(self):
        self.assertIn(
            "create_accommodation_item_defaults(allow_deferred=True)",
            inspect.getsource(setup.after_install),
        )
        self.assertIn(
            "create_accommodation_item_defaults()",
            inspect.getsource(setup_wizard.setup_wizard_complete),
        )

    def test_legacy_patch_delegates_to_permanent_install_seeder(self):
        with (
            patch.object(
                seed_accommodation_item_groups,
                "create_accommodation_item_defaults",
            ) as create_defaults,
            patch.object(frappe.db, "commit") as commit,
        ):
            seed_accommodation_item_groups.execute()

        create_defaults.assert_called_once_with()
        commit.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()
