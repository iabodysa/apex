# Copyright (c) 2026, AFMCO and contributors
"""A-286: the module breadcrumb target must be pinned in the shipped JSON.

Desk resolves a record's module crumb to ``module_wise_workspaces[module][0]``
(``frappe/public/js/frappe/views/breadcrumbs.js:161`` builds the href at :117),
and that list is EVERY public workspace of the module ordered by ``creation`` —
``Workspace.get_module_wise_workspaces`` filters only ``for_user`` and ``public``
(``frappe/desk/doctype/workspace/workspace.py:135-146``). A child workspace can
therefore win the crumb, which is how a Housing user opening a Building landed on
the hidden ``Backend Engines`` utility.

Nothing upstream orders that column. ``get_doc_files`` walks the workspace folder
with bare ``os.listdir`` (``frappe/model/sync.py:135``) — directory order, not
alphabetical: measured on this checkout it yields habitat, backend_engines,
housing, safety, custody, costs_and_leasing. And every later JSON change
re-imports as delete+insert (``import_file.py:238-239`` -> ``delete_old_doc``),
so ``db_insert`` re-stamps ``creation = now()`` for a row that ships no value
(``frappe/model/base_document.py:566``) and the module's landing workspace drops
to LAST. That is a guaranteed regression on the first edit after install, not a
coin flip.

The fix this guard protects is declarative: the landing workspace ships an
explicit past ``creation``, which frappe preserves verbatim on both install paths
because ``set_user_and_timestamp`` only overwrites it outside install/patch/migrate
(``frappe/model/document.py:601-604``), and ``db_insert`` only stamps ``now()``
when the value is empty. A pinned root therefore sorts first no matter what
``os.listdir`` returns and no matter how often anything re-imports — the ordering
survives the very act that used to break it, which a repair pass run afterwards
cannot promise.

Why a file-level scan rather than a bench assertion: the invariant is a property
of the shipped is_standard JSON, so it has to fail on the change that writes the
bad JSON rather than on a site that has already imported it. Stdlib-only for the
same reason (the ``workspace_reachability`` pattern).

``patches/v1_x/reorder_root_workspace_creation`` remains registered as the legacy
compensator for rows already in a database. It cannot cover this case: it abstains
on any module without exactly one public root, and Habitat has shipped two since
Backend Engines was relocated into it.
"""

import glob
import json
import os
import unittest
from datetime import datetime

_APP = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")

# An unpinned row is stamped at import time, so it sorts after every past pin and
# ties with every other unpinned row - both of which this guard must reject.
_IMPORT_TIME = datetime.max


def _parse(stamp):
    """Frappe writes microseconds; tolerate a hand-edit that drops them."""
    if not isinstance(stamp, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(stamp, fmt)
        except ValueError:
            continue
    return None


def _shipped_workspaces():
    """module -> [row], one row per is_standard workspace JSON on disk."""
    by_module = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("doctype") != "Workspace":
            continue
        by_module.setdefault(data.get("module"), []).append(
            {
                "name": data.get("name") or data.get("title"),
                "parent": (data.get("parent_page") or "").strip(),
                "public": bool(data.get("public")),
                "for_user": (data.get("for_user") or "").strip(),
                "hidden": bool(data.get("is_hidden")),
                "creation": data.get("creation"),
                "path": os.path.relpath(path, _APP),
            }
        )
    return by_module


def _breadcrumb_order(rows):
    """Rows sorted the way get_module_wise_workspaces orders them, unpinned last."""
    return sorted(rows, key=lambda r: (_parse(r["creation"]) or _IMPORT_TIME, r["name"]))


class TestBreadcrumbRootPin(unittest.TestCase):
    def setUp(self):
        self.by_module = _shipped_workspaces()
        self.assertTrue(self.by_module, f"no workspace JSON found under {_WORKSPACE_GLOB}")

    def _crumb_candidates(self, rows):
        """The rows frappe puts in module_wise_workspaces - public, not per-user."""
        return [r for r in rows if r["public"] and not r["for_user"]]

    def test_every_module_declares_one_visible_landing_root(self):
        """A module needs one unambiguous crumb target. Two visible roots means the
        answer is a guess, and zero means the crumb can only land on a child."""
        for module, rows in sorted(self.by_module.items()):
            candidates = self._crumb_candidates(rows)
            if not candidates:
                continue
            landing = [r for r in candidates if not r["parent"] and not r["hidden"]]
            self.assertEqual(
                len(landing),
                1,
                f"module {module!r} must ship exactly one public, visible, parent-less "
                f"workspace to be its breadcrumb target; found "
                f"{[r['path'] for r in landing]}",
            )

    def test_landing_root_sorts_before_every_sibling(self):
        """module_wise_workspaces[module][0] is the crumb href, so the landing root
        must hold the earliest creation among the module's public workspaces."""
        for module, rows in sorted(self.by_module.items()):
            candidates = self._crumb_candidates(rows)
            if not candidates:
                continue
            landing = [r for r in candidates if not r["parent"] and not r["hidden"]]
            if len(landing) != 1:
                continue  # reported by the declaration test, not re-reported here
            landing = landing[0]
            first = _breadcrumb_order(candidates)[0]
            self.assertEqual(
                first["name"],
                landing["name"],
                f"module {module!r}: Desk would send the module breadcrumb to "
                f"{first['name']!r} ({first['path']}), not to the landing root "
                f"{landing['name']!r} ({landing['path']}). Pin an earlier `creation` "
                f"on the landing root's JSON.",
            )
            pinned = _parse(landing["creation"])
            self.assertIsNotNone(
                pinned,
                f"module {module!r}: landing root {landing['path']} ships no parseable "
                f"`creation`, so its order is whatever os.listdir returned and any later "
                f"re-import moves it last",
            )
            for other in candidates:
                if other["name"] == landing["name"]:
                    continue
                self.assertLess(
                    pinned,
                    _parse(other["creation"]) or _IMPORT_TIME,
                    f"module {module!r}: {other['name']!r} ({other['path']}) does not sort "
                    f"strictly after the landing root {landing['name']!r}",
                )

    def test_no_pinned_creation_is_in_the_future(self):
        """An unpinned sibling is stamped at import time, so a future pin loses to it
        on every site until that date passes."""
        now = datetime.now()
        for module, rows in sorted(self.by_module.items()):
            for row in rows:
                if not row["creation"]:
                    continue
                pinned = _parse(row["creation"])
                self.assertIsNotNone(
                    pinned, f"{row['path']}: `creation` {row['creation']!r} is not a timestamp"
                )
                self.assertLess(
                    pinned,
                    now,
                    f"{row['path']} ({module}) pins a FUTURE `creation` {row['creation']!r}",
                )


if __name__ == "__main__":
    unittest.main()
