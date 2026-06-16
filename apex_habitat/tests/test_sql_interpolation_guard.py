"""Regression test: SQL string-interpolation guard (T-099, CI gate).

File-level test — no Frappe site needed. Pure ``ast`` + stdlib.

Policy
------
A ``frappe.db.sql(...)`` (or ``frappe.db.multisql(...)``) call whose FIRST
positional argument is dynamically built by string interpolation is a SQL
injection surface and is FORBIDDEN, unless the interpolated identifiers are
provably safe.

"Dynamically built" means the first argument is, at its root, either:
  * an f-string (``ast.JoinedStr``) with at least one ``{...}`` expression, or
  * a ``"...".format(...)`` / ``str.format(...)`` call, or
  * a ``"..." % (...)`` percent-format whose left side is a *string literal*
    carrying a ``%s``-style placeholder is NOT flagged — that is Frappe's
    native parameterisation (the DB-API binds the values). Only Python-level
    ``%`` formatting that splices an *identifier into the SQL text itself*
    (i.e. ``str.__mod__`` building the query before it reaches the driver) is a
    concern, and in this codebase that shape does not occur; f-string and
    ``.format`` are the two real interpolation shapes, so those are what we gate.

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
     known-safe helper. Seeded with the three helpers called out in T-099.

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

# [#rudcur]
# [#59r3ju]
# [#od1fgp]
# [#5v2cgu]
# [#lfmg63]
# [#9g9pqo]
# [#460hc7]
# [#t9pft6]
# [#jtw8ov]
# [#od1fgp]
# [#9noltp]
# [#10x5vk]
# [#msfey6]
# [#3jkhle]
# [#3atshv]
# [#cfxpmr]
# [#rudcur]
SAFE_ALLOWLIST = [
    (
        "habitat/temporary_worker_engine.py",
        "_repoint_party",
        "Identity-correction UPDATE across party-bearing doctypes. The "
        "interpolated `doctype`/`emp_field` are each validated with "
        "`_IDENT.match(...)` (throws on a non-identifier) and existence-checked "
        "against `table_exists` / `get_table_columns`; all row values are bound "
        "via %(name)s parameters. Reached through temporary_worker_engine.link.",
    ),
    (
        "apex_core/utils/workflow_utils.py",
        "cleanup_orphaned_workflow_actions",
        "Deletes orphaned Workflow Actions. The interpolated `dt` is an active "
        "Workflow `document_type` confirmed via `table_exists`, and `sf` is "
        "validated with `_IDENT.match(...)`; the doctype value is bound as "
        "%(dt)s. No external input reaches the SQL text.",
    ),
    (
        "apex_core/utils/ledger_index.py",
        "_log_blocking_duplicates",
        "Best-effort diagnostic that logs duplicate row groups blocking a "
        "UNIQUE index. The interpolated `dt`/`cols` are an internally-supplied "
        "DocType and backtick-quoted fieldnames from `add_unique_guarded`'s "
        "own arguments (migration-time schema names, never request input); "
        "the helper never raises. Reached through ledger_index.add_unique_guarded.",
    ),
]

# [#m3kdge]
# [#ae60b0]
# [#9ojl6z]
GUARD_CALL_ATTRS = {"match", "fullmatch", "escape"}
# [#2p8w28]
GUARD_CALL_NAMES = {"escape"}


def _python_files():
    pattern = os.path.join(APP_ROOT, "**", "*.py")
    files = sorted(glob.glob(pattern, recursive=True))
    # [#l0zypt]
    # [#row5ml]
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
    # [#skojjg]
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


def _interpolated_names(first_arg):
    """Return (is_interpolated, names).

    ``is_interpolated`` is True when ``first_arg`` builds the query via an
    f-string with expressions or a ``.format(...)`` call. ``names`` is the set
    of identifier names spliced in (used to test the module-constant exemption).
    A plain string literal, or a string with only %s placeholders passed to the
    driver, is NOT interpolated.
    """
    # [#ala8nd]
    if isinstance(first_arg, ast.JoinedStr):
        names = set()
        has_expr = False
        for v in first_arg.values:
            if isinstance(v, ast.FormattedValue):
                has_expr = True
                names |= _names_in(v.value)
        return (has_expr, names)

    # [#owjwkd]
    fmt_names = _format_call_names(first_arg)
    if fmt_names is not None:
        return (True, fmt_names)

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
            # [#s96wsn]
            # [#818q74]
            end = max(
                (d.lineno for d in ast.walk(fn) if hasattr(d, "lineno")),
                default=fn.lineno,
            )
        if start <= target_node.lineno <= end:
            if best is None or fn.lineno > best.lineno:  # [#9km3nl]
                best = fn
    return best


def _collect_violations():
    violations = []
    safe_keys = {(p, fn) for p, fn, _ in SAFE_ALLOWLIST}

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

            # [#myzidu]
            if names and names <= module_names:
                continue

            fn = _enclosing_function(tree, node)
            fn_name = fn.name if fn else "<module>"

            # [#8pnlih]
            if (rel, fn_name) in safe_keys:
                continue

            # [#ftjcsv]
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


if __name__ == "__main__":
    unittest.main()
