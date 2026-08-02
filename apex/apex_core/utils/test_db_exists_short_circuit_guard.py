# Copyright (c) 2026, AFMCO and contributors
"""A positional ``frappe.db.exists(dt, dn)`` can answer ``dn`` back without a query.

``database.py:1259-1261`` short-circuits on ``if dt != "DocType" and dt == dn:
return dn`` -- so a string ``dn`` that happens to equal its own doctype is reported
as an existing record on the strength of the string alone, no row required. The
class keeps producing live defects: a kiosk admitted a ghost record, a seed loader
read a real row as absent, and a whitelisted identifier cleared its own gate.

The settled idiom is the dict filter, ``exists(dt, {"name": dn})`` -- the only form
correct in BOTH directions (database.py:1253-1257). The tempting repair, rejecting
``dn == dt`` before the call, merely trades the false positive for a false negative:
a doctype whose record really is named after it then reads as absent.

This freezes the population. A call is a finding when its ``dn`` is neither provably
a filter dict nor provably a static string distinct from ``dt``. Every exemption is
a proof, not a taste:

* ``dt`` is the literal ``"DocType"``. The framework's own guard clause disables the
  short-circuit for that one doctype, so such a call always queries.
* ``dn`` is a dict literal, or a name whose every binding is a dict literal. A
  subscript or attribute target MUTATES rather than rebinds, so a filter assembled
  over several statements keeps its guarantee.
* ``dn`` is a static string different from ``dt``. Two literals cannot collide at
  runtime. Two EQUAL literals stay a finding, which is what makes this exemption
  self-proving rather than assumed.
* The test lane -- 385 of the 593 calls, which would add 213 findings. This is the
  one exemption that is a JUDGEMENT and not a proof: a wrong answer there fails its
  own test loudly, while every defect that prompted this guard shipped from a
  production path. Widening to the test lane needs those 213 rows, not a flag.

Resolution is single-file and scope-blind, so a name bound to a dict in one function
and to a fetched value in another reads as unknown everywhere: that costs precision,
never safety.

Invisible to it: a ``dn`` that crosses a function boundary, so a caller handing a
doctype name to a helper which probes positionally is named at the helper only. Case
folding is a SEPARATE defect the dict form does NOT fix: a string ``dn`` is
normalised to ``{"name": dn}`` regardless (query.py:113-114), so only the short-circuit differs.

Frozen-baseline ratchet: only a finding outside ``_BASELINE`` fails, and a baseline
entry that stops describing a real call fails too, so a fix must delete its own row.

Run standalone:  python3 -m unittest apex.apex_core.utils.test_db_exists_short_circuit_guard -v
"""

from __future__ import annotations

import ast
import unittest

from apex.tests.source_tree import all_py_files, is_test_file, parse, rel

# The one doctype the framework exempts from its own short-circuit (database.py:1259).
_SHORT_CIRCUIT_EXEMPT_DOCTYPE = "DocType"


def _is_db_exists(node):
    """``<anything>.db.exists(...)`` or a bare ``db.exists(...)``.

    Matched on the ``.db.exists`` shape rather than on an import, because the app
    reaches it as ``frappe.db.exists`` and as ``db.exists`` off a bound local, and
    both carry the same argument contract.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "exists"):
        return False
    base = func.value
    return (isinstance(base, ast.Attribute) and base.attr == "db") or (
        isinstance(base, ast.Name) and base.id == "db"
    )


def _is_dict_literal(node):
    """A dict display, or a ``dict(...)`` construction."""
    return isinstance(node, ast.Dict) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    )


def _bindings(tree):
    """``(dict_names, str_values, unknown_names)`` over the whole file.

    A name lands in ``unknown`` the moment ANY binding of it is not a literal, or
    two string bindings disagree, so a later read of it can only ever be believed
    when the file binds it one way throughout.
    """
    dicts: set[str] = set()
    strings: dict[str, str] = {}
    unknown: set[str] = set()

    def note(target, value):
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                note(element, None)
            return
        if not isinstance(target, ast.Name):
            # ``d["k"] = v`` and ``o.attr = v`` mutate an object; they do not rebind
            # the name, so a filter dict built up statement by statement survives.
            return
        name = target.id
        if _is_dict_literal(value):
            dicts.add(name)
        elif isinstance(value, ast.Constant) and isinstance(value.value, str):
            if strings.setdefault(name, value.value) != value.value:
                unknown.add(name)
        else:
            unknown.add(name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                note(target, node.value)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            note(node.target, node.value)
        elif isinstance(node, ast.AugAssign):
            note(node.target, None)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            note(node.target, None)
        elif isinstance(node, ast.withitem):
            if node.optional_vars is not None:
                note(node.optional_vars, None)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                unknown.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            unknown.update(node.names)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                unknown.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            unknown.add(node.name)
            arguments = getattr(node, "args", None)
            if arguments is not None:
                slots = (
                    list(arguments.posonlyargs)
                    + list(arguments.args)
                    + list(arguments.kwonlyargs)
                    + [arguments.vararg, arguments.kwarg]
                )
                unknown.update(slot.arg for slot in slots if slot is not None)
    return dicts, strings, unknown


def _static_str(node, strings, unknown):
    """The string this expression provably holds, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id not in unknown:
        return strings.get(node.id)
    return None


def _is_filter(node, dicts, unknown):
    """True when the argument provably reaches ``exists`` as a filter dict."""
    if _is_dict_literal(node):
        return True
    return isinstance(node, ast.Name) and node.id in dicts and node.id not in unknown


def _qualnames(tree):
    """``id(node) -> enclosing dotted qualname``, so a key survives a line shift."""
    names: dict[int, str] = {}

    def walk(parent, prefix):
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nested = f"{prefix}.{child.name}" if prefix else child.name
                names[id(child)] = nested
                walk(child, nested)
            else:
                names[id(child)] = prefix
                walk(child, prefix)

    walk(tree, "")
    return names


def _name_argument(node):
    """The ``dn`` this call passes, positionally or by keyword, else None."""
    if len(node.args) >= 2:
        return node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "dn":
            return keyword.value
    return None


def findings_in(tree, relpath, source):
    """``({key: names probed}, {key: file:line})`` for one parsed file.

    Keyed on ``path#qualname#doctype`` rather than on a line, so moving code
    inside a function never reds the ratchet, while renaming the function -- the
    moment the call deserves a fresh look -- does. Two calls sharing a key would
    hide behind one baseline row, so the VALUE lists every name probed under it:
    a second call added to an already-listed function changes the value and is
    reported, which comparing keys alone would have missed.

    Lines are carried separately, for the failure message only. A guard whose
    report cannot be walked back to a line is one the next author disables, but a
    line in the compared value would red the ratchet on every edit above it.

    The separator is ``#`` and not the ``::`` this reads like: a bare ``"::"``
    literal in a test file is the IPv6 unspecified address, and
    test_portal_token_throttle reads every address-shaped literal in the test tree
    as a throttle subnet seed. Its check is prefix-freeness, so ``"::"`` collides
    with every IPv6 seed any sibling file owns.
    """
    dicts, strings, unknown = _bindings(tree)
    qualnames = _qualnames(tree)
    probed: dict[str, list[str]] = {}
    lines: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not _is_db_exists(node) or not node.args:
            continue
        name_arg = _name_argument(node)
        if name_arg is None:
            continue
        doctype_arg = node.args[0]
        doctype = _static_str(doctype_arg, strings, unknown)
        if doctype == _SHORT_CIRCUIT_EXEMPT_DOCTYPE:
            continue
        if _is_filter(name_arg, dicts, unknown):
            continue
        name = _static_str(name_arg, strings, unknown)
        if name is not None and name != doctype:
            continue
        where = qualnames.get(id(node)) or "<module>"
        key = doctype if doctype is not None else ast.get_source_segment(source, doctype_arg)
        key = f"{relpath}#{where}#{key}"
        probed.setdefault(key, []).append(ast.get_source_segment(source, name_arg))
        lines.setdefault(key, []).append(node.lineno)
    return (
        {key: ", ".join(sorted(names)) for key, names in probed.items()},
        {
            key: f"{relpath}:{','.join(str(n) for n in sorted(numbers))}"
            for key, numbers in lines.items()
        },
    )


def sweep():
    """``(findings, locations, db_exists_calls_seen)`` over the production tree.

    The last value counts EVERY ``db.exists`` in the app, test lane included, so
    the floor below measures the matcher rather than the verdict.
    """
    findings: dict[str, str] = {}
    locations: dict[str, str] = {}
    seen = 0
    for path in all_py_files():
        tree = parse(path)
        if tree is None:
            continue
        calls = [node for node in ast.walk(tree) if _is_db_exists(node)]
        seen += len(calls)
        relpath = rel(path)
        if not calls or is_test_file(relpath):
            continue
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        found, where = findings_in(tree, relpath, source)
        findings.update(found)
        locations.update(where)
    return findings, locations, seen


# Measured 2026-07-31: 593 db.exists calls in the app; 385 in the test lane, 94
# already pass a filter dict, 47 probe "DocType" where the framework disables its
# own short-circuit, and 13 pass a static name. These 54 are the unproven remainder
# — pre-existing and unreviewed, NOT endorsed. Delete a row in the commit that
# converts its call to the dict form; test_baseline_holds_no_stale_entry insists.
_BASELINE: dict[str, str] = {
    "apex_core/doctype/masar_worker_token/masar_worker_token.py#get_or_create_for_driver#Salis Driver": "driver",
    "apex_core/doctype/masar_worker_token/masar_worker_token.py#get_or_create_for_employee#Employee": "employee",
    "apex_core/doctype/salis_settings/salis_settings.py#get_default_cost_center#Company": "company",
    "apex_core/setup/seed.py#_exists#doctype": "value",
    "apex_core/setup/seeders/auto_email_report_seed_base.py#seed_auto_email_reports_for#Report": 'cfg["report"]',
    "apex_core/setup/seeders/maintenance_material_template_seed.py#seed_templates#Maintenance Material Template": 'tpl["template_name"]',
    "apex_core/setup/seeders/salis_issue_seed.py#_grant_issue_role_perms#Role": "role",
    "apex_core/setup/seeders/salis_issue_seed.py#_pick_holiday_list#Holiday List": "hl",
    "apex_core/setup/seeders/salis_issue_seed.py#_seed_issue_priorities#Issue Priority": "name",
    "apex_core/setup/seeders/salis_issue_seed.py#_seed_issue_types#Issue Type": "name",
    "apex_core/setup/seeders/salis_issue_seed.py#_seed_sla#Issue Priority": "priority",
    "apex_core/setup/setup_wizard.py#_apply_deduction_policy#Company": "company",
    "apex_core/setup/setup_wizard.py#_apply_habitat_settings#Company": "company",
    "apex_core/setup/setup_wizard.py#_apply_salis_settings#Company": "company",
    "apex_core/setup/setup_wizard.py#_apply_salis_settings#Cost Center": "cost_center",
    "habitat/api/arrivals_desk.py#house_over_capacity#Room": "room",
    "habitat/doctype/building/building.py#_apply_capacity_reductions#Bed": "_surplus_code",
    "habitat/doctype/custody_return/custody_return.py#_validate_return_quantities#Custody Issue": "doc.custody_issue",
    "habitat/doctype/facility_asset_delivery/facility_asset_delivery.py#FacilityAssetDelivery.on_cancel#Facility Asset": "self.facility_asset",
    "habitat/doctype/facility_asset_movement/facility_asset_movement.py#_reconcile_origin#Room": "asset_room",
    "habitat/doctype/facility_asset_movement/facility_asset_movement.py#on_cancel#Facility Asset": "doc.facility_asset",
    "habitat/doctype/housing_assignment/housing_assignment.py#validate#Building": "doc.building",
    "habitat/doctype/housing_checkout/housing_checkout.py#create_departure_transport#Transport Request": "doc.departure_transport_request",
    "habitat/doctype/housing_checkout/housing_checkout.py#validate#Housing Assignment": "doc.assignment",
    "habitat/doctype/maintenance_material/maintenance_material_catalog.py#seed_catalog#Maintenance Material": 'item["material_name"]',
    "habitat/doctype/resident_request/resident_request.py#convert_request#source.target_doctype": "source.target_document",
    "habitat/doctype/safety_inspection_report/safety_inspection_report.py#SafetyInspectionReport._reverse_generated_request#Maintenance Request": "mr_name",
    "habitat/doctype/safety_task_execution/safety_task_execution.py#SafetyTaskExecution._has_linked_request#Maintenance Request": "mr_name",
    "habitat/doctype/utility_bill_entry/utility_bill_entry.py#_compute_variance#Utility Account": "doc.utility_account",
    "habitat/tasks/cost.py#allocate_building_accommodation_cost#Building": "building",
    "habitat/utils/finding_fanout.py#_already_linked#Maintenance Request": "mr_name",
    "logistay/doctype/telecom_contract/telecom_contract.py#refresh_sim_count#Telecom Contract": "contract",
    "patches/v1_0/seed_salis_authority_roles.py#execute#Role": "role_name",
    "patches/v1_0/seed_salis_roles.py#execute#Role": "role_name",
    "patches/v1_x/seed_demo_role_logins.py#_demo_rooms#Room": "room_number",
    "patches/v1_x/seed_demo_role_logins.py#_user#Role": "r",
    "patches/v1_x/seed_demo_role_logins.py#_user#User": "email",
    "patches/v2_0/fold_sim_operations_into_logistay.py#_drop_folded_workspaces#Workspace": "name",
    "patches/v2_0/migrate_sim_card_management.py#_classify#Supplier": "supplier",
    "patches/v2_0/migrate_sim_card_management.py#_migrate_row#Employee": "employee",
    "patches/v2_0/remove_kernel_landing_workspaces.py#execute#Workspace": "name",
    "salis/api/driver_portal/notifications.py#_owns_notification_reference#document_type": "filters",
    "salis/doctype/driver_clearance/driver_clearance.py#DriverClearance._release_driver#Salis Driver": "self.driver",
    "salis/doctype/driver_clearance/driver_clearance.py#DriverClearance._restore_driver#Salis Driver": "self.driver",
    "salis/doctype/rental_settlement/rental_settlement.py#RentalSettlement.create_payment_request#Salis Payment Request": "self.payment_request",
    "setup.py#create_accommodation_item_groups#Item Group": "group",
    "setup.py#create_accommodation_items#Item": 'record["item_code"]',
    "setup.py#create_custody_asset_categories#Custody Asset Category": "category_name",
    "setup.py#create_operational_depreciation_policies#Operational Depreciation Policy": 'policy["policy_name"]',
    "setup.py#create_role_profiles#Role Profile": "profile_name",
    "setup.py#create_roles#Role": "role_name",
}

# Well under the 593 counted, because this is not an inventory: it catches a matcher
# or a source_tree helper that stops finding calls at all, which would otherwise
# report an empty finding list as a clean tree.
_MINIMUM_CALLS_SEEN = 300


class TestDbExistsShortCircuitGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings, cls.locations, cls.seen = sweep()

    def test_no_new_unproven_name_probe(self):
        new = {
            key: value
            for key, value in self.findings.items()
            if _BASELINE.get(key) != value
        }
        self.assertEqual(
            new,
            {},
            "frappe.db.exists call(s) passing a name this scan cannot prove is a "
            "filter dict or a distinct static string. Such a call returns the name "
            "itself, unqueried, whenever it equals its doctype. Use the dict form "
            "exists(dt, {'name': dn}), which is correct in both directions:\n"
            + "\n".join(
                f"  {self.locations.get(key, key)}  {key} -> {new[key]}"
                for key in sorted(new)
            ),
        )

    def test_baseline_holds_no_stale_entry(self):
        stale = sorted(key for key in _BASELINE if key not in self.findings)
        self.assertEqual(
            stale,
            [],
            "these baseline entries no longer describe a real call; delete them in "
            "the commit that fixed or moved the call, so the ratchet cannot be "
            "walked back:\n" + "\n".join(f"  {key}" for key in stale),
        )

    def test_the_scan_still_finds_the_call_population(self):
        """Guard-of-the-guard: an empty finding list must mean clean, not blind."""
        self.assertGreater(
            self.seen,
            _MINIMUM_CALLS_SEEN,
            f"only {self.seen} db.exists calls were seen anywhere in the app. A "
            "renamed helper or a broken matcher would otherwise report a clean "
            "sweep over nothing.",
        )

    def test_the_classifier_exempts_only_what_it_can_prove(self):
        """Every exemption proved to exempt, on the shapes the app actually writes."""
        source = (
            'SAME = "Employee"\n'
            "def exempt(fetched):\n"
            '    frappe.db.exists("Employee", {"name": fetched})\n'
            "    built = {}\n"
            '    built["name"] = fetched\n'
            '    frappe.db.exists("Employee", built)\n'
            '    frappe.db.exists("DocType", fetched)\n'
            '    frappe.db.exists("Employee", "EMP-1")\n'
            '    frappe.db.exists({"doctype": "Employee", "name": fetched})\n'
            "def caught(fetched):\n"
            '    frappe.db.exists("Employee", SAME)\n'
        )
        found, locations = findings_in(ast.parse(source), "probe.py", source)
        # The dict, the dict assembled by subscript, the "DocType" carve-out and the
        # distinct static name are all exempt. A static name EQUAL to its doctype is
        # the short-circuit itself, so it must survive every one of them.
        self.assertEqual(found, {"probe.py#caught#Employee": "SAME"})
        self.assertEqual(locations, {"probe.py#caught#Employee": "probe.py:11"})

    def test_the_classifier_reports_what_it_claims_to_report(self):
        """A runtime name is a finding, by keyword too, and a second one is not hidden."""
        source = (
            "def one(fetched):\n"
            '    frappe.db.exists("Employee", fetched)\n'
            "def two(fetched, other):\n"
            '    frappe.db.exists("Employee", fetched)\n'
            '    frappe.db.exists("Employee", dn=other)\n'
            "def dynamic(doctype, fetched):\n"
            "    frappe.db.exists(doctype, fetched)\n"
        )
        found, locations = findings_in(ast.parse(source), "probe.py", source)
        self.assertEqual(
            found,
            {
                "probe.py#one#Employee": "fetched",
                # Both calls land on one key; listing the names is what stops the
                # second from hiding behind the first's baseline row.
                "probe.py#two#Employee": "fetched, other",
                "probe.py#dynamic#doctype": "fetched",
            },
        )
        # Both lines are carried, so the report names each offending call.
        self.assertEqual(locations["probe.py#two#Employee"], "probe.py:4,5")


if __name__ == "__main__":
    unittest.main()
