# Copyright (c) 2026, AFMCO and contributors
"""Every apex call into frappe must bind against the INSTALLED signature.

``frappe.desk.form.assign_to.add`` lost its ``ignore_permissions`` kwarg upstream --
a whitelisted function takes its kwargs from ``form_dict``, so the privileged flag
moved to a private ``_add``. The local bench still had it, CI resolves
``--frappe-branch version-15`` to that branch's HEAD at job time (test.yml:261-272),
and five tests errored ~900s into the suite on a ``TypeError`` no static gate could
have caught. Every kwarg the app passes into frappe is an unchecked assumption about
a dependency that moves under it.

This binds them. For each call whose callee resolves to a live ``frappe`` /
``erpnext`` / ``hrms`` object, ``inspect.signature(obj).bind_partial()`` is given the
call's positional COUNT and its keyword NAMES -- catching an unexpected keyword, too
many positionals, and a keyword colliding with a positional. Truth comes from the
installed callable, never a copied list, so it tracks whatever version CI resolves.

Deliberately conservative: a false red on an unpinned dependency would train the next
author to disable it, so every unknown is skipped rather than reported.

* An unresolvable callee, or one with no readable signature, is SKIPPED. Site-free
  that drops the ``frappe.db`` / ``frappe.qb`` / ``frappe.cache`` proxies -- ``local(...)``
  handles (frappe/__init__.py:177-186) with nothing behind them until a site binds;
  under ``bench run-tests`` they resolve and are checked. The floor on bound calls is
  what stops a wholesale resolution failure from reading as a clean scan.
* ``*args`` hides the positional count, so only keywords bind. ``**kwargs`` hides
  names, so the literal ones still bind and the rest are invisible.
* A name rebound anywhere in the file -- assigned, a parameter, a loop or ``with``
  target -- is dropped for that whole file, since this reads no scopes. That costs
  coverage (``for _ in ...`` drops the file's ``_()`` calls), never precision.

Invisible to it entirely: a callee reached through a value (``frappe.get_doc(...)
.insert()``), through ``getattr``, or through a name the app does not import
directly; and a kwarg that survives in the signature but changes MEANING.

Colocated, not central: ``tests/test_colocation_ratchet.py`` fails any new module
under ``apex/tests/`` and its ``_CEILING`` may only be lowered, so an app-wide guard
has no legal central home today. It sits in the shared kernel beside the other
app-wide static guard, ``test_cancel_refusal_guard.py``.

Run standalone:  python3 -m unittest apex.apex_core.utils.test_frappe_api_signature_compat -v
"""

from __future__ import annotations

import ast
import importlib
import inspect
import unittest

from apex.tests.source_tree import all_py_files, parse, rel

# The three apps CI installs from a moving branch head, so all three can drift the
# same way. required_apps in hooks.py names exactly these.
WATCHED_ROOTS = ("frappe", "erpnext", "hrms")

# Stands in for every argument value: binding checks arity and names, never types.
_ANY = object()


def _import_map(tree):
    """``{local name: dotted target}`` for every watched import in the file.

    Collected from the whole tree, so a function-local ``from frappe.desk.form
    import assign_to as _assign_to`` -- the exact shape the original defect used --
    is mapped like a module-level one.
    """
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in WATCHED_ROOTS:
                    out[alias.asname or root] = alias.name if alias.asname else root
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module.split(".")[0] not in WATCHED_ROOTS:
                continue
            for alias in node.names:
                if alias.name != "*":
                    out[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return out


def _rebound_names(tree):
    """Names the file binds to something other than an import.

    Whole-file and scope-blind on purpose: this walks no scopes, so the only safe
    reading of a name that is ever assigned is that a call through it may not be
    the import.
    """
    names = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            args = getattr(node, "args", None)
            if args:
                slots = (
                    list(args.args)
                    + list(args.posonlyargs)
                    + list(args.kwonlyargs)
                    + [args.vararg, args.kwarg]
                )
                names.update(arg.arg for arg in slots if arg is not None)
        elif isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [node.target]
        elif isinstance(node, ast.withitem):
            targets = [node.optional_vars] if node.optional_vars is not None else []
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                names.add(node.name)
        else:
            continue
        for target in targets:
            names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    return names


def _dotted_parts(func):
    """``a.b.c(...)`` as ``["a", "b", "c"]``; None when the base is not a plain name.

    A base that is itself a call or a subscript means the callee is a runtime value,
    which no static resolution can follow.
    """
    parts = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    parts.reverse()
    return parts


_resolved = {}


def _resolve(target):
    """The live object a dotted target names, or None when it cannot be reached.

    Imports the longest importable prefix and walks the rest with ``getattr``, so
    ``frappe.desk.form.assign_to.add`` resolves through the module and
    ``frappe.db.get_value`` through the bound proxy. Any failure means "unknown",
    never "broken": an unimportable module and an unbound proxy look the same here.
    """
    if target in _resolved:
        return _resolved[target]
    parts = target.split(".")
    obj = rest = None
    for cut in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except Exception:
            continue
        rest = parts[cut:]
        break
    if rest is None:
        _resolved[target] = None
        return None
    try:
        for attr in rest:
            obj = getattr(obj, attr)
    except Exception:
        obj = None
    _resolved[target] = obj
    return obj


def _readable_signature(obj):
    """The callable's signature, or None when this runtime cannot read one.

    Some C-implemented builtins reached through a proxy have none. They are counted
    as unresolved rather than as bound, so the floor below measures signatures
    actually READ and not merely objects reached.
    """
    try:
        return inspect.signature(obj)
    except (TypeError, ValueError):
        return None


def _bind_error(signature, positional_count, keyword_names):
    """The TypeError message when this call shape cannot bind, else None."""
    try:
        signature.bind_partial(
            *([_ANY] * positional_count), **{name: _ANY for name in keyword_names}
        )
    except TypeError as exc:
        return f"{signature} -- {exc}"
    return None


def scan():
    """``(findings, bound_call_count)`` over every apex Python file."""
    findings = []
    bound = 0
    for path in all_py_files():
        tree = parse(path)
        if tree is None:
            continue
        imports = _import_map(tree)
        if not imports:
            continue
        shadowed = _rebound_names(tree) - set(imports)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts = _dotted_parts(node.func)
            if not parts or parts[0] not in imports or parts[0] in shadowed:
                continue
            target = ".".join([imports[parts[0]]] + parts[1:])
            obj = _resolve(target)
            signature = _readable_signature(obj) if obj is not None else None
            if signature is None:
                continue
            starred = any(isinstance(arg, ast.Starred) for arg in node.args)
            keywords = [kw.arg for kw in node.keywords if kw.arg is not None]
            bound += 1
            error = _bind_error(signature, 0 if starred else len(node.args), keywords)
            if error:
                findings.append(f"{rel(path)}:{node.lineno}  {target}{error}")
    return findings, bound


# Measured 2026-07-31 against frappe 15.109.0: 11591 call sites bind under a bound
# site, 8621 site-free once the proxies drop out. The floor sits well under both --
# it catches a scan that resolves nothing and reports a clean sweep, and is
# deliberately not an inventory, so a real drift in either number does not red it.
_MINIMUM_BOUND_CALLS = 6000


class TestFrappeApiSignatureCompat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # tests/test_unit_test_coverage_guard.py re-runs every module that documents
        # a standalone command in an interpreter that BLOCKS frappe. With no
        # framework to read signatures from there is nothing to bind, and an empty
        # finding list would read as clean -- so stand the class down instead.
        if _resolve("frappe") is None:
            raise unittest.SkipTest("frappe is not importable, so no signature is installed")
        cls.findings, cls.bound = scan()

    def test_no_call_site_passes_an_argument_the_installed_signature_rejects(self):
        self.assertEqual(
            sorted(self.findings),
            [],
            "Call site(s) into frappe/erpnext/hrms that the INSTALLED signature "
            "cannot bind. CI resolves these apps to their version-15 branch HEAD at "
            "job time, so a kwarg removed upstream fails here first instead of as a "
            "TypeError deep in the suite. Fix the call, or the framework version:\n"
            + "\n".join("  " + f for f in sorted(self.findings)),
        )

    def test_the_scan_binds_a_substantial_share_of_the_call_sites(self):
        """Guard-of-the-guard: an empty finding list must mean clean, not blind."""
        self.assertGreater(
            self.bound,
            _MINIMUM_BOUND_CALLS,
            f"only {self.bound} call sites bound. Every unresolved callee is skipped "
            "silently, so a broken import map or a renamed source_tree helper would "
            "otherwise report a clean scan over nothing.",
        )

    def test_binding_rejects_the_shapes_it_claims_to_reject(self):
        """The discriminator itself: prove _bind_error is not always None."""

        def sample(first, *, allowed=None):
            return first, allowed

        signature = _readable_signature(sample)
        self.assertIsNone(_bind_error(signature, 1, ["allowed"]))
        self.assertIn("unexpected keyword", _bind_error(signature, 1, ["removed"]) or "")
        self.assertIn("too many positional", _bind_error(signature, 3, []) or "")
        self.assertIn("multiple values", _bind_error(signature, 1, ["first"]) or "")

    def test_an_aliased_function_local_import_still_resolves(self):
        """The original defect's exact shape: aliased, imported inside a function."""
        tree = ast.parse(
            "def handler():\n"
            "    from frappe.desk.form import assign_to as _assign_to\n"
            "    _assign_to.add({})\n"
        )
        self.assertEqual(
            _import_map(tree).get("_assign_to"), "frappe.desk.form.assign_to"
        )
        self.assertIsNotNone(_resolve("frappe.desk.form.assign_to.add"))


if __name__ == "__main__":
    unittest.main()
