# Copyright (c) 2026, AFMCO and contributors
"""Regression test: HTTP-method enforcement (#33).

File-level test — no Frappe site needed. Uses ast and stdlib only.

Policy: any @frappe.whitelist() endpoint that performs a write operation
(insert, save, delete, db_set, db_insert, submit, cancel, set_value) MUST
declare methods=["POST"] in the decorator.

A bare @frappe.whitelist() (without methods=) accepts GET and POST equally,
which means write side-effects can be triggered via a cacheable GET request —
a CSRF and cache-poisoning risk.
"""

import ast
import glob
import os
import unittest

import apex

# The INSTALLED package, never a path derived from this file. Walking up from here lands in
# .claude/tests/apex, which holds only tests, so every allowlist path failed os.path.exists
# and this guard — the one a dated incident earned — scanned nothing while reporting 40
# failures nobody could act on.
APP_ROOT = os.path.dirname(os.path.abspath(apex.__file__))

WRITE_CALLS = {
    "insert",
    "save",
    "submit",
    "cancel",
    "delete",
    "delete_doc",
    "db_set",
    "db_insert",
    "db_update",
    "set_value",
    "db_delete",
    "rename_doc",
    # Two writers this AST scan cannot reach by name alone: `get_document_share_key`
    # inserts a Document Share Key row through a doc method, and `notify_user_system`
    # inserts a Notification Log from another module (the delegate hop below only
    # resolves functions defined in the SAME file). Without them both endpoints read
    # as non-writing, and their allowlist entries silently stopped guarding anything.
    "get_document_share_key",
    "notify_user_system",
}

SAFE_ALLOWLIST = [
]


PERMISSION_CALLS = {"has_permission", "check_permission"}

PERMISSION_RECHECK_ALLOWLIST = [
    (
        "apex_core/setup/demo.py",
        "clear_demo_data",
        "Demo-data removal. Not a write to any one document, so there is no doc to "
        "permission-check: it is role-gated by frappe.only_for('System Manager') and "
        "then selects strictly on the dedicated demo user as record owner, refusing "
        "outright when that user is absent. Same gate ERPNext puts on its own "
        "clear_demo_data (erpnext/setup/demo.py:40).",
    ),
    (
        "habitat/web_form/accommodation_resident_request/accommodation_resident_request.py",
        "submit_resident_request",
        "Public QR intake. allow_guest; authorisation is the location token plus "
        "a honeypot + per-IP rate limit. A Guest has no role to permission-check.",
    ),
    (
        "salis/web_form/transport_request/transport_request.py",
        "submit_transport_request",
        "Public transport-request intake. allow_guest; token/honeypot/rate-limit "
        "guarded. A Guest has no role to permission-check.",
    ),
    (
        "salis/api/portal_notifications.py",
        "save_subscription",
        "Portal push subscription. allow_guest, so the session user is Guest and a "
        "has_permission call would grade Guest's rights rather than the holder's. "
        "Authorisation is the portal token — _resolve_identity refuses without one "
        "via resolve_portal_subject(required=True) — plus _belongs_to, which refuses "
        "a device already registered to another holder, and a 10-per-minute rate "
        "limit. The write targets only that holder's own subscription row.",
    ),
    (
        "salis/api/portal_notifications.py",
        "delete_subscription",
        "The removal half of the same subscription, gated identically: the portal "
        "token resolves the holder, _belongs_to refuses another holder's device, and "
        "the endpoint is rate-limited. A Guest session has no role to check.",
    ),
    (
        "salis/web_form/vehicle_incident/vehicle_incident.py",
        "submit_vehicle_incident",
        "Public vehicle-incident intake. allow_guest; honeypot + per-IP rate-limit, "
        "incident_type restricted to two safe options and free text bounded; inserts a "
        "docstatus-0 draft only (no on_submit side-effect). A Guest has no role to "
        "permission-check.",
    ),
    (
        "habitat/web_form/arrival_manifest/arrival_manifest.py",
        "submit_arrival_manifest",
        "Public arrival-manifest intake. allow_guest; honeypot + per-IP rate-limit, "
        "child rows capped and field-allowlisted (the read-only 'Arrived As' link can "
        "never be guest-seeded). A Guest has no role to permission-check.",
    ),
    (
        "salis/api/masar.py",
        "create_worker_request",
        "Masar guest endpoint. allow_guest; authorisation is the Masar worker "
        "token resolved server-side, not a desk permission.",
    ),
    (
        "salis/api/masar.py",
        "create_worker_transport_request",
        "Masar guest endpoint. allow_guest; the worker is resolved server-side from "
        "the token (_resolve_worker) and is the sole identity for the request — the "
        "client never supplies a worker id; explicit rate_limit. A Guest has no role "
        "to permission-check.",
    ),
    (
        "salis/api/masar.py",
        "notify_hr_iqama_expiring",
        "Masar guest endpoint. allow_guest; authorisation is the Masar worker "
        "token resolved server-side (_resolve_worker), scope derived server-side, "
        "explicit rate_limit. A Guest has no role to permission-check.",
    ),
    (
        "salis/api/masar.py",
        "submit_trip_rating",
        "Masar guest endpoint. allow_guest; the worker is resolved server-side from "
        "the token (_resolve_worker) and the write is refused unless that worker is on "
        "the trip's own Passenger Manifest (PermissionError otherwise); one rating per "
        "worker+trip, explicit rate_limit. A Guest has no role to permission-check.",
    ),
    (
        "salis/api/masar.py",
        "confirm_boarding",
        "Masar guest endpoint. allow_guest; authorisation is the Masar worker "
        "token resolved server-side (_resolve_worker), scope derived from the "
        "worker's own trip manifest, explicit rate_limit. A Guest has no role to "
        "permission-check.",
    ),
    (
        "salis/api/fleet_employee.py",
        "submit_fuel_request",
        "Fleet employee page (/fleet). The Salis Driver is resolved from the "
        "session server-side (get_driver_for_user, never client-supplied) and the "
        "vehicle must be the caller's own bound vehicle (raises PermissionError "
        "otherwise); the Fuel Request is created Pending for supervisor approval "
        "and the employee holds no create DocPerm, so authorisation is the "
        "server-side identity resolution, not a desk permission — the same rail "
        "the retired driver-portal fuel endpoint ran on. Identity-resolved writer.",
    ),
    (
        "salis/api/fleet_employee_services.py",
        "receive_vehicle",
        "Fleet employee page (/fleet). NOT a bypass — the write is checked by Frappe "
        "itself. The Salis Driver is resolved from the session server-side "
        "(base._session_driver) and the assignment must be his own and active "
        "(_validate_active_session_assignment raises otherwise); the Vehicle Handover "
        "is then inserted and submitted inside as_capacity(DRIVER) with NO "
        "ignore_permissions, so insert() grades the Driver role's own create DocPerm. "
        "This scan matches a literal has_permission call and cannot see a check the "
        "framework performs.",
    ),
    (
        "salis/api/fleet_employee_services.py",
        "return_vehicle",
        "The return half of the same handover, gated identically: session-resolved "
        "driver, own active assignment, and insert()+submit() inside "
        "as_capacity(DRIVER) with no ignore_permissions.",
    ),
    (
        "salis/api/fleet_employee_services.py",
        "submit_additional_fuel_request",
        "Fleet employee page. Session-resolved Salis Driver, quota checked server-side "
        "against his own period allowance, and the Fuel Request inserted inside "
        "as_capacity(DRIVER) with no ignore_permissions — the Driver role's own create "
        "DocPerm is what admits it. The row is created Pending for supervisor approval.",
    ),
    (
        "salis/api/fleet_employee_services.py",
        "report_incident",
        "Fleet employee page. Session-resolved Salis Driver, the incident is raised "
        "about his own bound vehicle, and the insert runs inside as_capacity(DRIVER) "
        "with no ignore_permissions.",
    ),
    (
        "salis/api/fleet_employee_services.py",
        "create_complaint",
        "Fleet employee page. THIS ONE IS A REAL BYPASS and is waived rather than "
        "excused: a complaint is an Issue, and granting the Driver role create on Issue "
        "would widen the surface further than the hole it closes, so the insert passes "
        "ignore_permissions. Authorisation is the session-resolved Salis Driver "
        "(base._session_driver) and the Issue is stamped to him, so he can raise one "
        "only as himself. The module docstring records the same reservation. Waived "
        "pending the narrower answer tracked on A-521.3.",
    ),
    (
        "salis/api/fleet_employee_services.py",
        "reply_to_complaint",
        "The reply half of the same complaint, and the same real bypass: a reply is a "
        "Communication, and Driver create on Communication would hand over the whole "
        "email and comment surface. _my_issue refuses any Issue not raised by the "
        "session-resolved driver before the Communication is inserted. Waived pending "
        "A-521.3.",
    ),
    (
        "salis/api/manual_boarding.py",
        "board_worker",
        "Supervisor manual boarding. allow_guest, so a has_permission call at this "
        "level would grade Guest rather than the actor; authorisation is delegated to "
        "boarding._resolve_trip(dispatch_trip, 'write'), which resolves the driver from "
        "his token and refuses a trip that is not his, and for a staff actor calls "
        "frappe.has_permission('Dispatch Trip', ptype, doc=..., throw=True) — so the "
        "framework check does run, one frame down. Only that trip's own log is written.",
    ),
    (
        "salis/api/driver_portal/execution.py",
        "start_my_trip",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); the Trip Start Log is the caller's "
        "own record. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal/execution.py",
        "complete_my_trip",
        "Driver portal. The Salis Driver is resolved from the session "
        "server-side and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); updates the caller's own Trip Start "
        "Log. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal/execution.py",
        "mark_stop_progress",
        "Driver portal. The Salis Driver is resolved from the session server-side "
        "and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); the Trip Stop Progress row is written "
        "on the caller's own open Trip Start Log. Token/identity-resolved writer.",
    ),
    (
        "salis/api/driver_portal/execution.py",
        "mark_arrived",
        "Driver portal. The Salis Driver is resolved from the session server-side "
        "and the trip is honoured only when it belongs to that driver "
        "(_resolve_my_trip raises otherwise); the arrival flag is written on the "
        "caller's own open Trip Start Log Trip Stop Progress row (same rail as "
        "mark_stop_progress). Token/identity-resolved writer.",
    ),
    (
        "salis/doctype/rental_settlement/rental_settlement.py",
        "create_payment_request",
        "Doc-bound whitelisted method (def create_payment_request(self)). Frappe "
        "requires access to `self` to call it, the raised request is inserted "
        "WITH permissions (no ignore_permissions), and it is gated on "
        "self.docstatus==1 / status=='Approved'. Not a free-floating writer.",
    ),
    (
        "salis/api/boarding_flow.py",
        "notify_remaining_passengers",
        "Driver action. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (own trip for a driver, any for Salis staff, "
        "raises PermissionError otherwise) before the write; only the trip's own "
        "Pending rows are nudged. Trip-scope-resolved writer.",
    ),
    (
        "salis/api/boarding_flow.py",
        "worker_request_wait",
        "Masar guest endpoint. allow_guest; the worker is resolved server-side from "
        "the Masar token (_resolve_worker, never client-supplied) and only their own "
        "row on their own today's trip is written; explicit rate_limit. A Guest has "
        "no role to permission-check.",
    ),
    (
        "salis/api/boarding_flow.py",
        "worker_claim_boarded",
        "Masar guest endpoint (worker self-confirm). allow_guest; the worker is "
        "resolved server-side from the Masar token (_resolve_worker) and only their "
        "own boarding event + boarding-state row on their own today's trip is "
        "written; explicit rate_limit. A Guest has no role to permission-check.",
    ),
    (
        "salis/api/boarding_flow.py",
        "driver_mark_not_boarded",
        "Driver exception override. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (own trip for a driver, any for Salis staff, "
        "raises PermissionError otherwise) before reversing a worker's self-confirm. "
        "Trip-scope-resolved writer.",
    ),
    (
        "salis/api/boarding_flow.py",
        "depart_and_finalize",
        "Driver action. The caller is authorised on the trip by "
        "_resolve_trip_for_driver (own trip for a driver, any for Salis staff, "
        "raises PermissionError otherwise) before the finalize write. "
        "Trip-scope-resolved writer.",
    ),
]


def _python_files():
    pattern = os.path.join(APP_ROOT, "**", "*.py")
    return sorted(glob.glob(pattern, recursive=True))


def _has_write_call(func_node):
    """Return True if the function body contains any recognised write call."""
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in WRITE_CALLS:
                    return True
            elif isinstance(node.func, ast.Name):
                if node.func.id in WRITE_CALLS:
                    return True
    return False


def _decorator_has_methods_post(decorator):
    """Return True if the decorator node contains methods=["POST"]."""
    if not isinstance(decorator, ast.Call):
        return False
    for keyword in decorator.keywords:
        if keyword.arg == "methods":
            val = keyword.value
            if isinstance(val, ast.List):
                for elt in val.elts:
                    if isinstance(elt, ast.Constant) and elt.value == "POST":
                        return True
    return False


def _is_bare_whitelist(decorator):
    """Return True if the decorator is @frappe.whitelist() without methods=.

    Matches:
        @frappe.whitelist()
        @frappe.whitelist(allow_guest=True)   — also unsafe for writes

    Does NOT match:
        @frappe.whitelist(methods=["POST"])
    """
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    is_whitelist = (
        (isinstance(func, ast.Attribute) and func.attr == "whitelist")
        or (isinstance(func, ast.Name) and func.id == "whitelist")
    )
    if not is_whitelist:
        return False
    return not _decorator_has_methods_post(decorator)


def _is_whitelisted(decorator):
    """True if the decorator is any @frappe.whitelist(...) / @whitelist(...)."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    return (
        (isinstance(func, ast.Attribute) and func.attr == "whitelist")
        or (isinstance(func, ast.Name) and func.id == "whitelist")
    )


def _called_local_funcs(func_node):
    """Names of bare-name function calls in the body, e.g. ``route_payment(x)``.

    Follows ONE level of intra-module delegation: a whitelisted endpoint
    that delegates its write to a module-level helper (``return route_payment(...)``)
    is still a write endpoint, and the permission check may legitimately live in
    either the endpoint or that helper.
    """
    out = set()
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            out.add(n.func.id)
    return out


def _has_permission_call(func_node):
    """True if the function body calls has_permission / check_permission."""
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in PERMISSION_CALLS:
                return True
            if isinstance(f, ast.Name) and f.id in PERMISSION_CALLS:
                return True
    return False


def _collect_permission_violations(allowlist=None):
    """Scan all Python files for whitelisted POST write endpoints that do not
    recheck permission (directly or via a one-hop module-level delegate) and are
    not in PERMISSION_RECHECK_ALLOWLIST.

    ``allowlist=[]`` answers what the guard WOULD report with no exemptions, which
    is how the liveness test reads every entry's effect in one scan.

    Returns a list of (rel_path, func_name, lineno).
    """
    violations = []
    entries = PERMISSION_RECHECK_ALLOWLIST if allowlist is None else allowlist
    allow_keys = {(p, fn) for p, fn, _ in entries}

    for fpath in _python_files():
        rel = os.path.relpath(fpath, APP_ROOT)
        with open(fpath, encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source, filename=fpath)
        except SyntaxError:
            continue

        local_funcs = {
            n.name: n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not any(_is_whitelisted(d) for d in node.decorator_list):
                continue

            writes = _has_write_call(node)
            delegates = _called_local_funcs(node)
            if not writes:
                for callee in delegates:
                    target = local_funcs.get(callee)
                    if target is not None and _has_write_call(target):
                        writes = True
                        break
            if not writes:
                continue

            if (rel, node.name) in allow_keys:
                continue

            checked = _has_permission_call(node)
            if not checked:
                for callee in delegates:
                    target = local_funcs.get(callee)
                    if target is not None and _has_permission_call(target):
                        checked = True
                        break
            if checked:
                continue

            violations.append((rel, node.name, node.lineno))

    return violations


def _collect_violations(allowlist=None):
    """Scan all Python files; return list of (rel_path, func_name, lineno).

    ``allowlist=[]`` answers what the guard would report with no exemptions.
    """
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
            continue  # Syntax errors caught by other tests / ruff

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            bare = [d for d in node.decorator_list if _is_bare_whitelist(d)]
            if not bare:
                continue
            if not _has_write_call(node):
                continue
            if (rel, node.name) in safe_keys:
                continue
            violations.append((rel, node.name, node.lineno))

    return violations


class TestHttpMethodEnforcement(unittest.TestCase):

    def test_no_write_endpoint_without_post_restriction(self):
        """All whitelisted write endpoints must declare methods=['POST'].

        If this test fails, the reported function performs database writes but
        its @frappe.whitelist() decorator does not restrict the HTTP method to
        POST. This means the write can be triggered via a GET request.

        Remediation options:
          1. Add methods=['POST'] to the decorator.
          2. If the function is actually read-only, add it to SAFE_ALLOWLIST
             in this test file with a comment explaining why it is safe.
        """
        violations = _collect_violations()
        if violations:
            details = "\n".join(
                f"  {rel}:{lineno}  def {fn}()" for rel, fn, lineno in violations
            )
            self.fail(
                f"Found {len(violations)} whitelisted write endpoint(s) without "
                f"methods=['POST']:\n{details}\n\n"
                "Add methods=['POST'] to the decorator, or add the function to "
                "SAFE_ALLOWLIST in test_http_enforcement.py with a justification."
            )

    def test_write_endpoints_recheck_permission(self):
        """Every non-allowlisted whitelisted write endpoint must recheck permission.

        A whitelisted endpoint that performs a write (directly, or via a one-hop
        module-level delegate such as ``create_routed_payment -> route_payment``)
        MUST call ``frappe.has_permission(...)`` / ``check_permission(...)`` so
        the Frappe permission system — including per-doc ``has_permission``
        hooks — gates the write. Being finance-approved / submitted is a property
        of the target document, NOT an authorisation of the caller.

        The only exemptions are the token-/identity-resolved guest writers in
        PERMISSION_RECHECK_ALLOWLIST, whose authorisation is a movement token or
        a server-side identity resolution rather than a desk permission.

        If this test fails, the reported endpoint writes without rechecking
        permission. Remediation:
          1. Add ``frappe.has_permission("<DocType>", "write", doc=<doc>,
             throw=True)`` (and a ``"submit"`` check if it submits) BEFORE any
             side effect.
          2. If it is a legitimately token/identity-resolved guest writer, add it
             to PERMISSION_RECHECK_ALLOWLIST with a justification.
        """
        violations = _collect_permission_violations()
        if violations:
            details = "\n".join(
                f"  {rel}:{lineno}  def {fn}()" for rel, fn, lineno in violations
            )
            self.fail(
                f"Found {len(violations)} whitelisted write endpoint(s) that do "
                f"not recheck permission:\n{details}\n\n"
                "Add frappe.has_permission(...) / check_permission(...) before "
                "the write, or add the endpoint to PERMISSION_RECHECK_ALLOWLIST "
                "in test_http_enforcement.py with a justification."
            )

    # One subTest run over both allowlist constants — `test_allowlist_entries_still_exist`
    # and `test_permission_recheck_allowlist_entries_still_exist` — rather than two
    # methods running the identical algorithm; every entry of both is still opened and
    # still named individually in the failure.
    def test_allowlist_entries_still_exist(self):
        """Every entry in either allowlist must still resolve to real code.

        Catches a stale exemption when a writer is renamed or removed — which would
        otherwise silently drop the endpoint out of the guarded set.
        """
        for label, entries in (
            ("SAFE_ALLOWLIST", SAFE_ALLOWLIST),
            ("PERMISSION_RECHECK_ALLOWLIST", PERMISSION_RECHECK_ALLOWLIST),
        ):
            for rel_path, func_name, _reason in entries:
                abs_path = os.path.join(APP_ROOT, rel_path)
                with self.subTest(allowlist=label, path=rel_path, func=func_name):
                    self.assertTrue(
                        os.path.exists(abs_path),
                        f"{label} references '{rel_path}' which does not exist.",
                    )
                    with open(abs_path, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read())
                    func_names = {
                        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    }
                    self.assertIn(
                        func_name,
                        func_names,
                        f"{label} references '{func_name}' in '{rel_path}' but the "
                        "function no longer exists.",
                    )

    def test_every_allowlist_entry_is_load_bearing(self):
        """No entry in either allowlist may outlive the finding it was written for.

        An exemption is a WAIVER, and this is its expiry rule. The repo has no
        time-based expiry and should not grow one: a date says nothing about
        whether the risk is still there, so it either fires while the hazard is
        live or lets it sit until the clock runs out. The checkable condition is
        the cause, not the calendar — an entry expires the moment removing it
        stops changing what the guard reports.

        A spent entry here is worse than clutter, because it can be spent for two
        opposite reasons. Either the endpoint stopped writing — in which case the
        exemption is over — or the DETECTOR stopped seeing the write, in which
        case the endpoint is unguarded and the entry is the only remaining record
        that it ever needed guarding. Both once shipped: two endpoints whose
        writes go through a doc method and a cross-module helper read as
        non-writing here for months. So a failure is NOT automatically a delete.
        Open the endpoint first, and only delete once you have confirmed it truly
        no longer writes; if it does, teach the detector (see WRITE_CALLS) and
        the entry becomes load-bearing again.

        The sibling above proves the entries still POINT at real code; this proves
        they still DO something. Reading it costs one extra scan per list, not one
        per entry: an allowlist is a per-key filter, so what the guard reports with
        no exemptions at all names every load-bearing entry at once.
        """
        for label, entries, unexempted in (
            (
                "SAFE_ALLOWLIST",
                SAFE_ALLOWLIST,
                {(r, f) for r, f, _ln in _collect_violations(allowlist=[])},
            ),
            (
                "PERMISSION_RECHECK_ALLOWLIST",
                PERMISSION_RECHECK_ALLOWLIST,
                {
                    (r, f)
                    for r, f, _ln in _collect_permission_violations(allowlist=[])
                },
            ),
        ):
            spent = [
                # " -> " and not "::": a bare double colon in any test file is read as
                # an IPv6 seed by the throttle suite's cross-file prefix-freeness check.
                f"  {rel} -> {fn}" for rel, fn, _reason in entries
                if (rel, fn) not in unexempted
            ]
            with self.subTest(allowlist=label):
                self.assertEqual(
                    spent,
                    [],
                    f"{label} entr(ies) no longer suppress anything — the guard "
                    "reports nothing for them even with the allowlist emptied:\n"
                    + "\n".join(spent)
                    + "\n\nRead the endpoint before deleting. If it genuinely no "
                    "longer writes, delete the entry. If it still writes, this "
                    "scan has gone blind to how — add that writer to WRITE_CALLS, "
                    "because right now the endpoint is guarded by nothing.",
                )


if __name__ == "__main__":
    unittest.main()
