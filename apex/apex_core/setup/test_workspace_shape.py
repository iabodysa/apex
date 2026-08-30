# Copyright (c) 2026, afmcoltd

import json
import pathlib

import frappe
from frappe.desk.desktop import get_desktop_page
from frappe.tests.utils import FrappeTestCase

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))

ROOTS = {"Apex Core", "Salis", "Habitat", "Logistay", "My Tasks"}

NAMED_BLOCKS = {
    "shortcut": ("shortcut_name", "shortcuts"),
    "card": ("card_name", "cards"),
    "chart": ("chart_name", "charts"),
    "number_card": ("number_card_name", "number_cards"),
    "quick_list": ("quick_list_name", "quick_lists"),
}


def _shipped_workspaces():
    found = {}
    for path in sorted(APP_ROOT.rglob("workspace/*/*.json")):
        data = json.loads(path.read_text())
        if data.get("doctype") == "Workspace" and data.get("public"):
            found[data["name"]] = data
    return found


class TestTheDeskTreeAFreshInstallProduces(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_the_shipped_workspace_files_are_still_on_disk(self):
        self.assertGreaterEqual(len(_shipped_workspaces()), 10)

    def test_every_root_workspace_hangs_under_apex(self):
        live = set(frappe.get_all("Workspace", filters={"parent_page": "Apex"}, pluck="name"))
        self.assertEqual(ROOTS - live, set())

    def test_no_root_workspace_would_render_blank(self):
        blank = []
        for name in ROOTS:
            doc = frappe.get_doc("Workspace", name)
            if not doc.links and not doc.shortcuts:
                blank.append(name)
        self.assertEqual(blank, [])

    def test_the_apex_landing_page_carries_a_text_block(self):
        apex = frappe.get_doc("Workspace", "Apex")
        text = [
            block
            for block in json.loads(apex.content or "[]")
            if block.get("type") in ("header", "paragraph")
        ]
        self.assertTrue(text)

    def test_every_content_block_names_an_item_the_page_returns(self):
        shipped = _shipped_workspaces()
        checked = 0
        orphans = []
        for name in shipped:
            if not frappe.db.exists("Workspace", name):
                continue
            page = get_desktop_page(json.dumps({"name": name}))
            doc = frappe.get_doc("Workspace", name)
            for block in json.loads(doc.content or "[]"):
                key, plural = NAMED_BLOCKS.get(block.get("type"), (None, None))
                if not key:
                    continue
                checked += 1
                wanted = (block.get("data") or {}).get(key)
                labels = {item.get("label") for item in page.get(plural, {}).get("items", [])}
                if wanted not in labels:
                    orphans.append(f"{name}/{block['type']}:{wanted}")
        self.assertEqual(orphans, [], f"blocks checked: {checked}")
        self.assertGreaterEqual(checked, 190)
