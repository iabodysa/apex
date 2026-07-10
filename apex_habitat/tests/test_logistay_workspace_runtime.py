# Copyright (c) 2026, AFMCO and contributors
"""Runtime regression: Logistay workspace opens and resolves (P-196).

DB-backed — asserts the imported Workspace doc loads, its content blob
parses, and every shortcut/link link_to target exists as a live DocType or
Report. Static JSON checks (test_workspace_visibility.py) do not catch a
migrate-import failure or a dangling link_to; this does.
"""

import json
import unittest

import frappe


class TestLogistayWorkspaceRuntime(unittest.TestCase):

    def test_workspace_loads_and_resolves(self):
        doc = frappe.get_doc("Workspace", "Logistay")
        self.assertEqual(doc.module, "Logistay")
        self.assertEqual(doc.public, 1)
        self.assertEqual(doc.is_hidden, 0)

        blocks = json.loads(doc.content)
        self.assertGreater(len(blocks), 0, "Logistay workspace content blob is empty")

        for shortcut in doc.shortcuts:
            if shortcut.type == "DocType":
                self.assertTrue(
                    frappe.db.exists("DocType", shortcut.link_to),
                    f"shortcut '{shortcut.label}' points at missing DocType '{shortcut.link_to}'",
                )
            elif shortcut.type == "Report":
                self.assertTrue(
                    frappe.db.exists("Report", shortcut.link_to),
                    f"shortcut '{shortcut.label}' points at missing Report '{shortcut.link_to}'",
                )

        for link in doc.links:
            if link.link_type == "DocType" and link.link_to:
                self.assertTrue(
                    frappe.db.exists("DocType", link.link_to),
                    f"link '{link.label}' points at missing DocType '{link.link_to}'",
                )


if __name__ == "__main__":
    unittest.main()
