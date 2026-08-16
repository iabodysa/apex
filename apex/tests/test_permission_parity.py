# Copyright (c) 2026, AFMCO Support Services Co. Ltd

import ast
import json
import unittest
from pathlib import Path

import apex

PKG_ROOT = Path(apex.__file__).resolve().parent
PKG_NAME = PKG_ROOT.name
HOOKS = PKG_ROOT / "hooks.py"
PERMISSIONS_PY = PKG_ROOT / "habitat" / "permissions.py"

GUARDED_MAPS = ("permission_query_conditions", "has_permission", "doc_events")

CORE_ALLOWLIST = {
    "Address": "frappe",
    "Issue": "frappe",
    "Employee": "hrms",  # Portal credential lifecycle revocation
    "Sales Invoice": "erpnext",  # Logistay invoice issuance gate (P-191)
    "Additional Salary": "hrms",  # Logistay payroll/WPS validate gate (P-192)
    "Report": "frappe",  # A-201 report-role runnability guard (apex-owned refs only)
    # on_cancel: lets Accounts cancel a payment a Telecom Contract billing log still cites.
    "Payment Entry": "erpnext",
}

HARDCODED_PERMISSION_DOCTYPE_LITERALS = {
    "Building",
}


def _owned_doctypes():
    """Names of every DocType whose JSON lives under apex/**/doctype/<slug>/<slug>.json."""
    owned = set()
    for jp in PKG_ROOT.glob("**/doctype/*/*.json"):
        if jp.stem != jp.parent.name:
            continue
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if data.get("doctype") == "DocType" and data.get("name"):
            owned.add(data["name"])
    return owned


def _string_constants(tree):
    """Module-level ``NAME = "dotted.path"`` bindings in hooks.py.

    hooks.py names the shared scope handlers once and reuses the name across two dozen
    DocTypes. Without resolving those names a static reader sees an ``ast.Name`` where it
    expected a literal, which is how this guard stopped loading at all.
    """
    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def _handler_literal(node, constants):
    """The dotted handler a hooks.py value names, or None when it is not a string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _load_hook_maps():
    """AST-parse hooks.py and return {map_name: {doctype: [handler_dotted_path, ...]}}.

    Static parse (no import) so it needs neither frappe nor a live site. doc_events values
    are nested {event: handler} dicts; the two permission maps are flat {doctype: handler},
    whose values may be either a literal or a module-level name bound to one.
    """
    tree = ast.parse(HOOKS.read_text(encoding="utf-8"), filename=str(HOOKS))
    constants = _string_constants(tree)
    wanted = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id in GUARDED_MAPS:
                wanted[tgt.id] = node.value
    out = {}
    for name in GUARDED_MAPS:
        val = wanted.get(name)
        assert isinstance(val, ast.Dict), f"hooks.py: {name} is not a dict literal"
        entries = {}
        for k, v in zip(val.keys, val.values):
            assert isinstance(k, ast.Constant) and isinstance(k.value, str), (
                f"{name}: non-string doctype key"
            )
            doctype = k.value
            handlers = []
            if name == "doc_events":
                assert isinstance(v, ast.Dict), f"{name}[{doctype!r}] is not a dict"
                for hv in v.values:
                    literal = _handler_literal(hv, constants)
                    if literal is not None:
                        handlers.append(literal)
            else:
                literal = _handler_literal(v, constants)
                assert literal is not None, (
                    f"{name}[{doctype!r}] handler is neither a string nor a module-level "
                    "name bound to one"
                )
                handlers.append(literal)
            entries[doctype] = handlers
        out[name] = entries
    return out


def _module_defined_names(module_dotted):
    """Top-level names defined in an apex module, or None if the file is missing.

    Resolves `apex.a.b` -> apex/a/b.py (or a/b/__init__.py) and AST-collects
    every top-level def/class/assignment/import alias. Used to prove a hooked handler's
    attribute still exists after a rename, without importing (no frappe needed).
    """
    parts = module_dotted.split(".")
    assert parts[0] == PKG_NAME, f"handler not in {PKG_NAME}: {module_dotted}"
    rel = parts[1:]
    cand = PKG_ROOT.joinpath(*rel).with_suffix(".py")
    if not cand.is_file():
        cand = PKG_ROOT.joinpath(*rel, "__init__.py")
    if not cand.is_file():
        return None
    tree = ast.parse(cand.read_text(encoding="utf-8"), filename=str(cand))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
    return names


def _is_permissions_handler(handler):
    """True when a dotted handler lives in a *.permissions module (the scoping family)."""
    return handler.rsplit(".", 1)[0].endswith(".permissions")


class TestPermissionParity(unittest.TestCase):
    """Static guard proving hooks.py permission wiring survives a DocType rename."""

    @classmethod
    def setUpClass(cls):
        cls.owned = _owned_doctypes()
        cls.maps = _load_hook_maps()
        cls.allowed = cls.owned | set(CORE_ALLOWLIST)

    def test_every_hook_key_is_owned_or_allowlisted(self):
        offenders = []
        for map_name, entries in self.maps.items():
            for doctype in entries:
                # "*" is Frappe's GLOBAL wildcard: doc_events["*"] registers a handler on
                # EVERY doctype (the A-083 app-wide native-submit/native-cancel workflow
                # guard, merged with the per-doctype events). It is a legitimate
                # cross-cutting registration, not a stale post-rename doctype key.
                if doctype == "*":
                    continue
                if doctype not in self.allowed:
                    offenders.append(f"{map_name}[{doctype!r}]")
        self.assertFalse(
            offenders,
            "hooks.py names doctype(s) that are neither apex-owned nor in CORE_ALLOWLIST "
            "(stale key after a rename fails OPEN = cross-building exposure); add to "
            f"CORE_ALLOWLIST only if legitimately a core doctype: {sorted(offenders)}",
        )

    def test_every_handler_target_resolves(self):
        broken = []
        for map_name, entries in self.maps.items():
            for doctype, handlers in entries.items():
                for h in handlers:
                    module, _, attr = h.rpartition(".")
                    names = _module_defined_names(module)
                    if names is None:
                        broken.append(f"{map_name}[{doctype!r}] -> module missing: {module}")
                    elif attr not in names:
                        broken.append(f"{map_name}[{doctype!r}] -> {module} has no {attr!r}")
        self.assertFalse(
            broken,
            f"hooks.py points at handler(s) that no longer exist (renamed/moved): {sorted(broken)}",
        )

    def test_query_and_haspermission_family_parity(self):
        pqc_family = {
            dt
            for dt, hs in self.maps["permission_query_conditions"].items()
            if any(_is_permissions_handler(h) for h in hs)
        }
        hp_family = {
            dt
            for dt, hs in self.maps["has_permission"].items()
            if any(_is_permissions_handler(h) for h in hs)
        }
        missing_hp = sorted(pqc_family - hp_family)
        missing_pqc = sorted(hp_family - pqc_family)
        self.assertEqual(
            (missing_hp, missing_pqc),
            ([], []),
            "scoping-family parity broken: "
            f"have permission_query_conditions but NO has_permission={missing_hp}; "
            f"have has_permission but NO permission_query_conditions={missing_pqc}",
        )

    def test_hardcoded_permission_literals_track_owned_doctypes(self):
        src = PERMISSIONS_PY.read_text(encoding="utf-8")
        stale_checklist = sorted(
            lit for lit in HARDCODED_PERMISSION_DOCTYPE_LITERALS if f'"{lit}"' not in src
        )
        self.assertFalse(
            stale_checklist,
            "HARDCODED_PERMISSION_DOCTYPE_LITERALS lists a literal no longer in "
            f"permissions.py (checklist is stale, re-derive it): {stale_checklist}",
        )
        orphaned = sorted(
            lit for lit in HARDCODED_PERMISSION_DOCTYPE_LITERALS if lit not in self.allowed
        )
        self.assertFalse(
            orphaned,
            "permissions.py hardcodes a doctype-name string that is no longer an owned/"
            "allowlisted doctype (a rename left the literal behind -> scope filter matches "
            f"nothing, fails CLOSED): {orphaned}",
        )



if __name__ == "__main__":
    unittest.main(verbosity=2)
