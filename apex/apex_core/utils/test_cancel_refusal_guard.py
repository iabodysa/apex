# Copyright (c) 2026, AFMCO and contributors
"""``on_cancel`` must not refuse a cancellation — the refusal belongs in ``before_cancel``.

Frappe dispatches ``before_cancel`` from ``run_before_save_methods()``
(frappe/model/document.py:414), writes the row with ``db_update()`` (:428), and
only then dispatches ``on_cancel`` from ``run_post_save_methods()`` (:431). A
``frappe.throw`` from ``on_cancel`` therefore fires with ``docstatus`` 2 already
in the open transaction and the child rows written. Rollback still undoes the
row, so this is not corruption — it is the wrong seam, and everything reading
the voucher later in that request sees a refused document as cancelled. The line
to hold: ``before_cancel`` REFUSES, ``on_cancel`` RESTORES.

Colocated beside ``workflow_guard.py``, which owns the app-wide ``before_cancel``
at ``hooks.py:94``. Not in ``apex/tests/``: ``test_colocation_ratchet.py`` fails
any new central module, and its ``_CEILING`` may only be lowered.

Flags a handler whose own body raises, or that calls an ``apex`` function whose
body raises, within ``_DEPTH`` levels. Handlers are the ``on_cancel`` method, the
detached module-level ``on_cancel``, and whatever ``hooks.py`` wires to
``on_cancel`` under any name. Callees resolve statically: ``self.x()``, a
same-module ``x()``, ``<first param>.x()`` against a same-module class, a name
imported from ``apex``, and ``alias.x()`` on an imported ``apex`` module.

Does NOT catch, at any depth: a refusal behind a framework call (``doc.save()``,
``frappe.get_doc(...).cancel()``), behind ``getattr`` or dynamic dispatch, or in
a callee outside ``apex``. ``frappe.msgprint(raise_exception=True)`` is not read
as a raise — the app does not use it, and guessing kwargs would cost precision.

``_DEPTH`` is 1 by measurement, not by taste: depth 0 finds nothing, depth 1
finds the one real offender, depth 2+ adds only the stock engine's positivity
backstop, which is deliberate cover for a caller that reaches the ledger with no
cancel at all. So 1 is the widest depth that reports only refusals.

Frozen-baseline ratchet: only a finding outside ``_BASELINE`` fails, and
``test_baseline_holds_no_stale_entry`` fails on an entry that stops describing a
real finding.

Run standalone:  python3 -m unittest apex.apex_core.utils.test_cancel_refusal_guard -v
"""

from __future__ import annotations

import ast
import os
import unittest

from apex.tests.source_tree import (
    APP_ROOT,
    file_dotted_path,
    parse,
    production_py_files,
    rel,
)

HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")

# How many apex call levels below the handler a raise still counts. 1 is the
# handler's own body plus its direct apex callees. Raising it widens the scan;
# the docstring above says what no value can reach.
_DEPTH = 1

# The cancel hook under the ban, and the one a refusal moves to.
_BANNED_HOOK = "on_cancel"
_REFUSAL_HOOK = "before_cancel"

# Ways to end a request with an error. `throw` covers `from frappe import throw`.
_THROW_NAMES = frozenset({"frappe.throw", "throw"})

# {"<dotted.module>:<qualname>": "why this one still stands"}
# One entry, a DEFERRAL not an exception: the sweep that moved six stock-voucher
# refusals into before_cancel read only handler BODIES, so this seventh - a throw
# one call down, in _release_recovery_advance - was never seen. Same defect, and
# it stays only because vehicle_incident is outside this change's write scope.
# Fix: move the paid/recovered check to before_cancel, then delete this entry.
_BASELINE: dict[str, str] = {
    "apex.salis.doctype.vehicle_incident.vehicle_incident:VehicleIncident.on_cancel": (
        "refuses when the linked Employee Advance already carries a paid or "
        "recovered amount; belongs in before_cancel"
    ),
}


def _dotted(node):
    """``a.b.c`` for an attribute/name chain, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _apex_imports(tree):
    """``{local_name: dotted_apex_target}`` for every apex import in the module."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("apex."):
                    found[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("apex"):
            for alias in node.names:
                found[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return found


class _Module:
    """One parsed production file: its functions by qualname, plus its apex imports."""

    def __init__(self, path, tree):
        self.path = path
        self.dotted = file_dotted_path(path)
        self.imports = _apex_imports(tree)
        self.funcs = {}
        self.methods_by_name = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.funcs[f"{node.name}.{sub.name}"] = sub
                        self.methods_by_name.setdefault(sub.name, []).append(node.name)


def _index():
    """Every production module, keyed by dotted path. Tests are out of scope —
    a test file may raise as much as it likes."""
    modules = {}
    for path in production_py_files():
        tree = parse(path)
        if tree is not None:
            mod = _Module(path, tree)
            modules[mod.dotted] = mod
    return modules


def _hooked_handlers(index):
    """``{(dotted_module, funcname)}`` wired to the banned hook by doc_events.

    Read from the AST, never by importing hooks.py: this guard runs with no site.
    A doc_events handler is a cancel handler whatever it is named, and at least
    one is wired under a name of its own rather than as ``on_cancel``.
    """
    tree = parse(HOOKS_PY)
    wired = set()
    if tree is None:
        return wired
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == _BANNED_HOOK):
                continue
            targets = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
            for target in targets:
                if not (isinstance(target, ast.Constant) and isinstance(target.value, str)):
                    continue
                module, _, func = target.value.rpartition(".")
                if module in index:
                    wired.add((module, func))
    return wired


def cancel_handlers(index):
    """``[(module, qualname, node)]`` — everything Frappe dispatches on cancel."""
    wired = _hooked_handlers(index)
    handlers = []
    for dotted, mod in index.items():
        for qualname, node in mod.funcs.items():
            named = qualname.rpartition(".")[2] == _BANNED_HOOK
            if named or (dotted, qualname) in wired:
                handlers.append((mod, qualname, node))
    return sorted(handlers, key=lambda h: (h[0].dotted, h[1]))


def _raises_directly(node):
    """``[(kind, lineno)]`` for every raise / frappe.throw in this body."""
    hits = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Raise):
            hits.append(("raise", sub.lineno))
        elif isinstance(sub, ast.Call) and _dotted(sub.func) in _THROW_NAMES:
            hits.append(("frappe.throw", sub.lineno))
    return hits


def _lookup(mod, qualname):
    node = mod.funcs.get(qualname) if mod else None
    return (mod, qualname, node) if node is not None else None


def _imported(index, mod, local, attr=None):
    """Resolve a bare name, or ``alias.attr``, that arrived through an apex import."""
    target = mod.imports.get(local)
    if target is None:
        return None
    if attr is not None:
        return _lookup(index.get(target), attr)
    module, _, func = target.rpartition(".")
    return _lookup(index.get(module), func)


def _resolve(index, mod, owner, call):
    """The apex function a call reaches, as ``(module, qualname, node)`` or None."""
    name = _dotted(call.func)
    if name is None:
        return None
    head, _, tail = name.rpartition(".")
    if head == "self" and owner:
        return _lookup(mod, f"{owner}.{tail}")
    if not head:
        return _lookup(mod, tail) or _imported(index, mod, tail)
    if head in mod.imports:
        return _imported(index, mod, head, tail)
    # `doc.x()` in a detached handler: doc is this module's own controller.
    for klass in mod.methods_by_name.get(tail, []):
        return _lookup(mod, f"{klass}.{tail}")
    return None


def findings(index, depth=_DEPTH):
    """``{"<module>:<qualname>": [reason, ...]}`` per cancel handler that can refuse."""
    found = {}
    for mod, qualname, node in cancel_handlers(index):
        reasons = []
        seen = {(mod.dotted, qualname)}
        frontier = [(mod, qualname, node, qualname.rpartition(".")[0], [])]
        for level in range(depth + 1):
            nxt = []
            for cur_mod, cur_qual, cur_node, cur_owner, path in frontier:
                for kind, lineno in _raises_directly(cur_node):
                    where = " -> ".join(path + [cur_qual])
                    reasons.append(f"{kind} at {rel(cur_mod.path)}:{lineno} via {where}")
                if level == depth:
                    continue
                for sub in ast.walk(cur_node):
                    if not isinstance(sub, ast.Call):
                        continue
                    hit = _resolve(index, cur_mod, cur_owner, sub)
                    if hit is None or (hit[0].dotted, hit[1]) in seen:
                        continue
                    seen.add((hit[0].dotted, hit[1]))
                    nxt.append(
                        (hit[0], hit[1], hit[2], hit[1].rpartition(".")[0],
                         path + [cur_qual])
                    )
            frontier = nxt
        if reasons:
            found[f"{mod.dotted}:{qualname}"] = reasons
    return found


class TestCancelHandlersNeverRefuse(unittest.TestCase):
    def test_no_cancel_handler_can_raise(self):
        """A cancel handler that can refuse is the regression this guard exists for."""
        new = {k: v for k, v in findings(_index()).items() if k not in _BASELINE}
        self.assertEqual(
            {},
            new,
            "on_cancel must not refuse a cancellation: by the time it runs, "
            "db_update() has stamped docstatus 2 into the open transaction "
            "(frappe/model/document.py:428, then :431 dispatches on_cancel). Move "
            f"the refusal to {_REFUSAL_HOOK}, dispatched at :414 before the write, "
            f"and leave {_BANNED_HOOK} restoration-only. Offenders: "
            + "; ".join(f"{k} [{', '.join(v)}]" for k, v in sorted(new.items())),
        )

    def test_baseline_holds_no_stale_entry(self):
        """A drained entry must leave, or the frozen set stops meaning one thing."""
        found = findings(_index())
        stale = sorted(key for key in _BASELINE if key not in found)
        self.assertEqual(
            [],
            stale,
            "these baseline entries no longer describe a real finding; delete them "
            f"so the frozen set keeps ratcheting: {stale}",
        )

    def test_the_scan_reaches_both_handler_shapes(self):
        """A guard scanning nothing passes forever — prove the universe is real.

        Both shapes must appear: the controller method and the detached
        module-level function hooks.py wires. The app uses each in dozens of
        places, so a resolver bug dropping either would leave this guard blind
        over half its subject while still reporting green.
        """
        handlers = cancel_handlers(_index())
        methods = [q for _m, q, _n in handlers if "." in q]
        detached = [q for _m, q, _n in handlers if "." not in q]
        self.assertGreater(len(methods), 10, "no on_cancel controller methods found")
        self.assertGreater(len(detached), 5, "no detached on_cancel functions found")

    def test_a_planted_refusal_is_detected(self):
        """The detector's own proof: a synthetic handler with a throw must be found.

        Without this, a resolver that silently returned nothing would ship a
        guard that can never fail — the exact defect this guard was written
        against. Depth 0 must MISS the callee and depth 1 must catch it, which
        also proves the depth knob is wired to the traversal.
        """
        tree = ast.parse(
            "import frappe\n"
            "def _blocked():\n"
            "    frappe.throw('no')\n"
            "class Voucher:\n"
            "    def on_cancel(self):\n"
            "        _blocked()\n"
        )
        index = {"apex.synthetic": _Module(os.path.join(APP_ROOT, "synthetic.py"), tree)}
        self.assertEqual(
            [], sorted(findings(index, depth=0)), "depth 0 must not see the callee"
        )
        self.assertEqual(
            ["apex.synthetic:Voucher.on_cancel"],
            sorted(findings(index, depth=1)),
            "depth 1 must follow the handler into its same-module callee",
        )


if __name__ == "__main__":
    unittest.main()
