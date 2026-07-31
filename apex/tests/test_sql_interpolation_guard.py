# Copyright (c) 2026, AFMCO and contributors
"""Regression test: SQL string-interpolation guard (CI gate).

File-level test — no Frappe site needed. Pure ``ast`` + stdlib.

Policy
------
A ``frappe.db.sql(...)`` (or ``frappe.db.multisql(...)``) call whose FIRST
positional argument is dynamically built by string interpolation is a SQL
injection surface and is FORBIDDEN, unless the interpolated identifiers are
provably safe.

"Dynamically built" means the first argument is, at its root, one of:
  * an f-string (``ast.JoinedStr``) with at least one ``{...}`` expression,
  * a ``"...".format(...)`` / ``str.format(...)`` call,
  * a ``+`` concatenation that splices a dynamic value into the SQL text
    (``"SELECT ... " + dt``), or
  * a ``%`` format that builds the SQL text in Python (``"... %s" % dt``).

Native parameterisation is NOT flagged: a plain ``"... %s"`` / ``"... %(x)s"``
string literal passed to ``frappe.db.sql`` with the values as the SECOND argument
is an ``ast.Constant`` (not a BinOp), so the DB-API binds the values and the query
text never carries the input. Only Python-level building of the query string
before it reaches the driver (f-string, ``.format``, ``+``, ``%``) is a concern.

Such a call is allowed only when ONE of the following holds:

  1. Every interpolated name resolves to a MODULE-LEVEL constant (a name bound
     at module scope — typically an UPPER_SNAKE constant such as a fixed table
     name). A literal constant cannot carry attacker input.

  2. The interpolation is GUARDED inside the same function by an identifier
     allowlist check — a call to an identifier regex (``_IDENT.match`` /
     ``re.match`` / ``re.fullmatch``) or an escaping helper
     (``frappe.db.escape`` / a ``*escape*`` call) — so a non-identifier value
     is rejected (or escaped) before it reaches the SQL text. This is the
     project's canonical "validate the doctype/fieldname against ``_IDENT``
     then f-string it" pattern.

  3. The enclosing function is named in ``SAFE_ALLOWLIST`` — a reviewed,
     known-safe helper, kept only while it still suppresses a finding.

If none holds, the call is a violation and this test fails, naming the file,
line, and function so the author either parameterises the query (bind values
with ``%s`` / ``%(name)s`` and pass them as the second argument), guards the
interpolated identifiers, or — only after security review — adds the helper to
``SAFE_ALLOWLIST`` with a justification.

This is the always-on CI counterpart to the periodic deep injection audit.
"""

import ast
import glob
import os
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# An entry belongs here ONLY while it is load-bearing — while deleting it would make
# `_collect_violations` report its call. A kept-past-its-cause entry is not inert: it is
# checked BEFORE the rule-2 guard check below, so it would go on suppressing the call if
# the guard the reviewer relied on were later removed. Four entries were dropped once
# their cause was gone (three functions moved to `frappe.qb`; one is now covered by
# rule 2's own `_IDENT.match` check). test_every_allowlist_entry_is_load_bearing enforces it.
# [#o9meu1]
SAFE_ALLOWLIST = [
    (
        "apex_core/utils/ledger_index.py",
        "_index_exists",
        "SHOW INDEX existence probe. The interpolated `dt` is an internally-"
        "supplied DocType name from a controller `on_doctype_update` (migration-"
        "time schema name, never request input); the index name is bound as %s. "
        "Wrapped in try/except, never raises. Reached through add_index_guarded.",
    ),
    (
        "apex_core/utils/ledger_index.py",
        "add_index_guarded",
        "Adds a plain composite performance index via ALTER TABLE at migration "
        "time. The interpolated `dt`/`idx`/`cols` are internally-supplied DocType, "
        "index and backtick-quoted fieldnames from the calling `on_doctype_update` "
        "(schema names, never request input); DDL error is caught, rolled back and "
        "logged. Reached through a controller on_doctype_update, not any request.",
    ),
    (
        "habitat/api/dashboard.py",
        "get_custody_value_in_employee_hands",
        "Interpolates `_building_condition()` which escapes every building name "
        "with `frappe.db.escape()` before injecting it into the WHERE clause "
        "(see permissions.py:136). Unscoped users receive '' (no filter); scoped "
        "users with no buildings receive '1=0'. No external input reaches SQL text.",
    ),
    (
        "habitat/api/dashboard.py",
        "get_top_custody_holders_by_value",
        "Same as get_custody_value_in_employee_hands: interpolates "
        "`_building_condition()` whose values are all `frappe.db.escape()`-d "
        "building names from User Permission records, never raw request input.",
    ),
]

# [#2m5lk7]
GUARD_CALL_ATTRS = {"match", "fullmatch", "escape"}
# [#i1lqzu]
GUARD_CALL_NAMES = {"escape"}


def _python_files():
    pattern = os.path.join(APP_ROOT, "**", "*.py")
    files = sorted(glob.glob(pattern, recursive=True))
    # [#4x1u6c]
    out = []
    for f in files:
        rel = os.path.relpath(f, APP_ROOT)
        base = os.path.basename(f)
        if rel.startswith("tests" + os.sep) or base.startswith("test_"):
            continue
        out.append(f)
    return out


def _is_frappe_db_sql(call):
    """True for a ``frappe.db.sql(...)`` / ``frappe.db.multisql(...)`` call."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {"sql", "multisql"}:
        return False
    # [#gl32l1]
    inner = func.value
    return isinstance(inner, ast.Attribute) and inner.attr == "db"


def _format_call_names(node):
    """If ``node`` is a ``<expr>.format(...)`` call, return the set of names
    referenced inside its ``.format`` arguments AND in any leading attribute
    chain (the format-spec identifiers come from the args). Else return None."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if not (isinstance(f, ast.Attribute) and f.attr == "format"):
        return None
    names = set()
    for arg in node.args:
        names |= _names_in(arg)
    for kw in node.keywords:
        names |= _names_in(kw.value)
    return names


def _binop_names(node):
    """If ``node`` builds a string with ``+`` concatenation or ``%`` formatting
    that splices a dynamic value into the SQL text *before* it reaches the driver
    (``"SELECT ... " + dt`` or ``"... %s" % dt``), return the interpolated names;
    else None.

    A pure literal concatenation (``"a" "b"``) carries no dynamic value and is not
    interpolation. Native parameterisation — a plain ``"... %s"`` string literal
    passed with a values second argument — is an ``ast.Constant``, not a BinOp, so
    it never reaches here and is never flagged.
    """
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Add, ast.Mod)):
        return None
    has_str = any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) for n in ast.walk(node)
    )
    has_dynamic = any(
        isinstance(n, (ast.Name, ast.Call, ast.Attribute, ast.Subscript))
        for n in ast.walk(node)
    )
    if not (has_str and has_dynamic):
        return None
    return _names_in(node)


def _interpolated_names(first_arg):
    """Return (is_interpolated, names).

    ``is_interpolated`` is True when ``first_arg`` builds the query via an
    f-string with expressions, a ``.format(...)`` call, ``+`` string
    concatenation, or ``%`` formatting that splices a value into the SQL text.
    ``names`` is the set of identifier names spliced in (used to test the
    module-constant exemption). A plain string literal, or a string with only %s
    placeholders passed to the driver as the second argument, is NOT interpolated.
    """
    # [#i51q46]
    if isinstance(first_arg, ast.JoinedStr):
        names = set()
        has_expr = False
        for v in first_arg.values:
            if isinstance(v, ast.FormattedValue):
                has_expr = True
                names |= _names_in(v.value)
        return (has_expr, names)

    # [#b8hqzg]
    fmt_names = _format_call_names(first_arg)
    if fmt_names is not None:
        return (True, fmt_names)

    # [#k1g0tw]
    bin_names = _binop_names(first_arg)
    if bin_names is not None:
        return (True, bin_names)

    return (False, set())


def _names_in(node):
    """All ``ast.Name`` ids referenced anywhere under ``node``."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
    return out


def _module_level_names(tree):
    """Names bound at module scope: top-level assignments, imports, and defs.

    A name in this set, when interpolated, is a constant the author controls —
    not request input — so it is a safe splice (e.g. a fixed table name).
    """
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names |= _assign_target_names(t)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _assign_target_names(target):
    out = set()
    if isinstance(target, ast.Name):
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for e in target.elts:
            out |= _assign_target_names(e)
    return out


def _function_has_guard(func_node):
    """True if the function body calls an identifier-allowlist / escape guard."""
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in GUARD_CALL_ATTRS:
                return True
            if isinstance(f, ast.Name) and f.id in GUARD_CALL_NAMES:
                return True
    return False


def _enclosing_function(tree, target_node):
    """Return the nearest enclosing FunctionDef for ``target_node`` (by lineno
    containment), or None if the call sits at module scope."""
    best = None
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = fn.lineno
        end = getattr(fn, "end_lineno", None)
        if end is None:
            # [#2nygtb]
            end = max(
                (d.lineno for d in ast.walk(fn) if hasattr(d, "lineno")),
                default=fn.lineno,
            )
        if start <= target_node.lineno <= end:
            if best is None or fn.lineno > best.lineno:  # [#9km3nl]
                best = fn
    return best


def _collect_violations(allowlist=None):
    """``allowlist=[]`` answers what the guard WOULD report with no exemptions —
    which is how the liveness test below reads every entry's effect in one scan."""
    violations = []
    entries = SAFE_ALLOWLIST if allowlist is None else allowlist
    safe_keys = {(p, fn) for p, fn, _ in entries}

    for fpath in _python_files():
        rel = os.path.relpath(fpath, APP_ROOT)
        with open(fpath, encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source, filename=fpath)
        except SyntaxError:
            continue

        module_names = _module_level_names(tree)

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_frappe_db_sql(node)):
                continue
            if not node.args:
                continue  # [#ayzxvh]
            first = node.args[0]
            is_interp, names = _interpolated_names(first)
            if not is_interp:
                continue

            # [#3iuyy9]
            if names and names <= module_names:
                continue

            fn = _enclosing_function(tree, node)
            fn_name = fn.name if fn else "<module>"

            # [#ejqirz]
            if (rel, fn_name) in safe_keys:
                continue

            # [#63u385]
            if fn is not None and _function_has_guard(fn):
                continue

            violations.append((rel, fn_name, node.lineno))

    return violations


class TestSqlInterpolationGuard(unittest.TestCase):

    def test_no_unguarded_interpolated_db_sql(self):
        """No ``frappe.db.sql`` may interpolate an unguarded identifier.

        A failure means the named call builds its SQL text with an f-string or
        ``.format`` splicing a value that is neither a module-level constant nor
        guarded by an identifier allowlist / escape.

        Remediation:
          1. Parameterise: keep the SQL a static string with ``%s`` / ``%(x)s``
             placeholders and pass the values as the second argument so the DB
             driver binds them.
          2. If a DocType / fieldname genuinely must be spliced into the text,
             validate it first against the project identifier regex
             (``_IDENT.match(...)``, throwing on mismatch) or escape it.
          3. Only after security review, add the helper to ``SAFE_ALLOWLIST``
             in this file with a justification.
        """
        violations = _collect_violations()
        if violations:
            details = "\n".join(
                f"  {rel}:{lineno}  in {fn}()" for rel, fn, lineno in violations
            )
            self.fail(
                f"Found {len(violations)} unguarded interpolated frappe.db.sql "
                f"call(s):\n{details}\n\n"
                "Parameterise the query, guard the interpolated identifier with "
                "an identifier allowlist / escape, or add the helper to "
                "SAFE_ALLOWLIST in test_sql_interpolation_guard.py with a "
                "justification."
            )

    def test_detector_flags_concat_and_percent(self):
        """``+`` concatenation and ``%`` formatting of the SQL text are
        detected as interpolation, while native ``%s`` binding (values passed as
        the second argument) and literal-only concatenation are not."""
        for snippet in (
            'frappe.db.sql("SELECT * FROM `tab" + dt + "`")',
            'frappe.db.sql("SELECT * FROM `tab%s`" % dt)',
        ):
            first = ast.parse(snippet).body[0].value.args[0]
            is_interp, names = _interpolated_names(first)
            self.assertTrue(is_interp, f"interpolation not detected: {snippet}")
            self.assertIn("dt", names)
        # [#56f5cn]
        safe = ast.parse('frappe.db.sql("SELECT * FROM t WHERE x = %s", (val,))')
        self.assertFalse(
            _interpolated_names(safe.body[0].value.args[0])[0],
            "native %s binding must not be flagged",
        )
        # [#p742ee]
        lit = ast.parse('frappe.db.sql("SELECT 1" + " FROM t")')
        self.assertFalse(
            _interpolated_names(lit.body[0].value.args[0])[0],
            "literal-only concatenation must not be flagged",
        )

    def test_allowlist_entries_still_exist(self):
        """Every SAFE_ALLOWLIST entry must still resolve to a real function.

        Catches stale entries when a helper is renamed or removed (which would
        silently widen the guard's blind spot).
        """
        for rel_path, func_name, _reason in SAFE_ALLOWLIST:
            abs_path = os.path.join(APP_ROOT, rel_path)
            with self.subTest(path=rel_path, func=func_name):
                self.assertTrue(
                    os.path.exists(abs_path),
                    f"SAFE_ALLOWLIST references '{rel_path}' which does not exist.",
                )
                with open(abs_path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                func_names = {
                    n.name
                    for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                self.assertIn(
                    func_name,
                    func_names,
                    f"SAFE_ALLOWLIST references '{func_name}' in '{rel_path}' "
                    "but the function no longer exists.",
                )

    def test_every_allowlist_entry_is_load_bearing(self):
        """No SAFE_ALLOWLIST entry may outlive the finding it was written for.

        An exemption is a WAIVER, and this is its expiry rule. The repo has no
        time-based expiry and should not grow one: a date says nothing about
        whether the risk is still there, so it either fires while the hazard is
        live or lets it sit until the clock runs out. The checkable condition is
        the cause, not the calendar — an entry expires the moment removing it
        stops changing what the guard reports.

        Letting a spent entry sit is not merely untidy. ``_collect_violations``
        consults the allowlist BEFORE the rule-2 guard check, so an entry kept
        past its cause is a live suppressor: the day someone drops the
        ``_IDENT.match`` a reviewer relied on, the finding reopens under rule 2
        — unless a forgotten waiver swallows it first, with no review and no
        sign that anything changed.

        The sibling above proves the entry still POINTS at real code; this proves
        it still DOES something. Reading it costs one extra scan, not one per
        entry: the allowlist is a per-key filter, so what the guard reports with
        no exemptions at all names every load-bearing entry at once.
        """
        unexempted = {(rel, fn) for rel, fn, _ln in _collect_violations(allowlist=[])}
        spent = [
            f"  {rel}::{fn}" for rel, fn, _reason in SAFE_ALLOWLIST
            if (rel, fn) not in unexempted
        ]
        self.assertEqual(
            spent,
            [],
            "SAFE_ALLOWLIST entr(ies) no longer suppress anything — the guard "
            "reports nothing for them even with the allowlist emptied:\n"
            + "\n".join(spent)
            + "\n\nDelete each one. Whatever made it necessary is gone (the SQL was "
            "parameterised, moved to frappe.qb, or now passes the identifier-guard "
            "rule on its own), and leaving it in place would silently re-suppress "
            "the call if that protection were ever removed.",
        )


if __name__ == "__main__":
    unittest.main()
