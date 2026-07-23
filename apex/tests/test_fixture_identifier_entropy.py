"""Static guard for random identifiers used by persistent test fixtures."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


MIN_RANDOM_CHARACTERS = 12
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _test_files() -> list[Path]:
    files = set(PACKAGE_ROOT.rglob("test_*.py"))
    files.update(PACKAGE_ROOT.rglob("*_test.py"))
    return sorted(files)


def _literal_int(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _hash_length_node(node: ast.Call) -> ast.AST | None:
    if _call_name(node) != "generate_hash":
        return None
    for keyword in node.keywords:
        if keyword.arg == "length":
            return keyword.value
    return node.args[0] if node.args else None


def _parameter_default(function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str) -> ast.AST | None:
    positional = [*function.args.posonlyargs, *function.args.args]
    default_offset = len(positional) - len(function.args.defaults)
    for index, argument in enumerate(positional):
        if argument.arg == parameter and index >= default_offset:
            return function.args.defaults[index - default_offset]
    for argument, default in zip(function.args.kwonlyargs, function.args.kw_defaults, strict=True):
        if argument.arg == parameter:
            return default
    return None


def _helper_names(tree: ast.AST) -> tuple[set[str], list[str]]:
    helpers: set[str] = set()
    violations: list[str] = []
    for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            length_node = _hash_length_node(call)
            if not isinstance(length_node, ast.Name):
                continue
            parameter_names = {
                argument.arg for argument in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
            }
            if length_node.id not in parameter_names:
                continue
            helpers.add(function.name)
            default = _literal_int(_parameter_default(function, length_node.id))
            if default is None or default < MIN_RANDOM_CHARACTERS:
                violations.append(
                    f"line {function.lineno}: random helper {function.name} must default to at least "
                    f"{MIN_RANDOM_CHARACTERS} characters"
                )
    return helpers, violations


def _assigned_random_names(tree: ast.AST, helper_names: set[str]) -> set[str]:
    names: set[str] = set()
    for assignment in (node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))):
        value = assignment.value
        if not isinstance(value, ast.Call) or _call_name(value) not in {"generate_hash", *helper_names}:
            continue
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _short_slice_bound(node: ast.Subscript) -> int | None:
    if not isinstance(node.slice, ast.Slice) or node.slice.lower is not None or node.slice.step is not None:
        return None
    return _literal_int(node.slice.upper)


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    helper_names, violations = _helper_names(tree)
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        name = _call_name(call)
        if name == "generate_hash":
            length_node = _hash_length_node(call)
            if isinstance(length_node, ast.Name):
                continue
            length = _literal_int(length_node)
            if length is None or length < MIN_RANDOM_CHARACTERS:
                violations.append(
                    f"line {call.lineno}: generate_hash length must be at least {MIN_RANDOM_CHARACTERS}"
                )
        elif name in helper_names:
            length_node = call.args[0] if call.args else next(
                (keyword.value for keyword in call.keywords if keyword.arg in {"n", "length"}), None
            )
            if length_node is None:
                continue
            length = _literal_int(length_node)
            if length is None or length < MIN_RANDOM_CHARACTERS:
                violations.append(
                    f"line {call.lineno}: random helper {name} length must be at least "
                    f"{MIN_RANDOM_CHARACTERS}"
                )

    random_names = _assigned_random_names(tree, helper_names)
    for subscript in (node for node in ast.walk(tree) if isinstance(node, ast.Subscript)):
        bound = _short_slice_bound(subscript)
        if bound is None or bound >= MIN_RANDOM_CHARACTERS:
            continue
        value = subscript.value
        is_random_name = isinstance(value, ast.Name) and value.id in random_names
        is_random_call = isinstance(value, ast.Call) and _call_name(value) in {"generate_hash", *helper_names}
        if is_random_name or is_random_call:
            violations.append(
                f"line {subscript.lineno}: random identifier is narrowed to {bound} characters"
            )

    return violations


class TestFixtureIdentifierEntropy(unittest.TestCase):
    def test_random_fixture_identifiers_have_twelve_characters(self):
        offenders = []
        for path in _test_files():
            for violation in _violations(path):
                offenders.append(f"{path.relative_to(PACKAGE_ROOT.parent)}: {violation}")

        self.assertEqual(offenders, [], "Low-entropy test fixture identifiers:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
