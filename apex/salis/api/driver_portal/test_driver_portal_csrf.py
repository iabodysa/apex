# Copyright (c) 2026, AFMCO and contributors
"""Import-safe security inventory for the guest driver portal."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
DRIVER_PORTAL = ROOT / "apex" / "salis" / "api" / "driver_portal"
BOARDING = ROOT / "apex" / "salis" / "api" / "boarding.py"
BOARDING_FLOW = ROOT / "apex" / "salis" / "api" / "boarding_flow.py"
MASAR = ROOT / "apex" / "salis" / "api" / "masar.py"
SERVED_DRIVER_ASSETS = ROOT / "apex" / "public" / "worker_portal" / "assets"

DRIVER_PORTAL_ENDPOINTS = {
    ("__init__.py", "mark_arrived"),
    ("__init__.py", "save_push_subscription"),
    ("attendance.py", "get_today_attendance"),
    ("attendance.py", "my_attendance"),
    ("attendance.py", "driver_check_in"),
    ("attendance.py", "driver_check_out"),
    ("boarding.py", "manual_boarding_sheet"),
    ("boarding.py", "manual_board_workers"),
    ("clearance.py", "get_my_clearance_certificate"),
    ("clearance.py", "my_clearance"),
    ("execution.py", "start_my_trip"),
    ("execution.py", "complete_my_trip"),
    ("execution.py", "push_driver_position"),
    ("execution.py", "mark_stop_progress"),
    ("fuel.py", "submit_fuel_request"),
    ("fuel.py", "my_fuel_quota"),
    ("fuel.py", "my_fuel_requests"),
    ("home.py", "get_my_today"),
    ("notifications.py", "get_my_notifications"),
    ("notifications.py", "get_push_config"),
    ("notifications.py", "delete_push_subscription"),
    ("profile.py", "get_driver_context"),
    ("profile.py", "get_driver_profile"),
    ("profile.py", "get_my_vehicle"),
    ("support.py", "my_support_tickets"),
    ("support.py", "raise_support_ticket"),
    ("support.py", "get_ticket"),
    ("support.py", "reply_to_ticket"),
    ("support.py", "report_vehicle_problem"),
    ("support.py", "request_license_renewal"),
    ("trips.py", "my_trips_today"),
    ("trips.py", "my_trips_recent"),
    ("trips.py", "my_worker_route_today"),
    ("trips.py", "my_trip_route"),
}

MIXED_DRIVER_ENDPOINTS = {
    ("boarding.py", "get_boarding_pass"),
    ("boarding.py", "scan_boarding_pass"),
    ("boarding_flow.py", "get_trip_boarding"),
    ("boarding_flow.py", "notify_remaining_passengers"),
    ("boarding_flow.py", "driver_mark_not_boarded"),
    ("boarding_flow.py", "depart_and_finalize"),
}

MIXED_WORKER_ENDPOINTS = {
    ("boarding_flow.py", "worker_request_wait"),
    ("boarding_flow.py", "worker_claim_boarded"),
    ("boarding_flow.py", "worker_trip_boarding"),
}

DRIVER_WRITERS = {
    ("__init__.py", "mark_arrived"),
    ("__init__.py", "save_push_subscription"),
    ("attendance.py", "driver_check_in"),
    ("attendance.py", "driver_check_out"),
    ("boarding.py", "manual_board_workers"),
    ("clearance.py", "get_my_clearance_certificate"),
    ("execution.py", "start_my_trip"),
    ("execution.py", "complete_my_trip"),
    ("execution.py", "push_driver_position"),
    ("execution.py", "mark_stop_progress"),
    ("fuel.py", "submit_fuel_request"),
    ("notifications.py", "delete_push_subscription"),
    ("support.py", "raise_support_ticket"),
    ("support.py", "reply_to_ticket"),
    ("support.py", "report_vehicle_problem"),
    ("support.py", "request_license_renewal"),
    ("boarding.py", "scan_boarding_pass"),
    ("boarding_flow.py", "notify_remaining_passengers"),
    ("boarding_flow.py", "driver_mark_not_boarded"),
    ("boarding_flow.py", "depart_and_finalize"),
}

TIGHT_DRIVER_WRITERS = {
    ("__init__.py", "save_push_subscription"),
    ("attendance.py", "driver_check_in"),
    ("attendance.py", "driver_check_out"),
    ("boarding.py", "manual_board_workers"),
    ("clearance.py", "get_my_clearance_certificate"),
    ("execution.py", "start_my_trip"),
    ("fuel.py", "submit_fuel_request"),
    ("support.py", "raise_support_ticket"),
    ("support.py", "reply_to_ticket"),
    ("support.py", "report_vehicle_problem"),
    ("support.py", "request_license_renewal"),
}

# Endpoints that charge their ceiling in the FUNCTION BODY instead of via @rate_limit,
# each mapped to the call that must do the charging. The decorator cannot express these:
# its identity is the request IP plus a form_dict lookup, and neither reaches the actor
# these endpoints must meter. Listing one here is an obligation, not an excuse — the
# mapped calls are asserted in the body below, so an endpoint that leaves
# PER_IP_DRIVER_ENDPOINTS still has to arrive somewhere that checks it.
BODY_RATE_LIMITED_DRIVER_ENDPOINTS = {
    ("boarding.py", "scan_boarding_pass"): (
        "_enforce_scan_actor_rate_limit",
        "_enforce_scan_unresolved_ip_rate_limit",
    ),
    ("boarding.py", "get_boarding_pass"): ("_enforce_pass_read_rate_limit",),
}
BODY_RATE_LIMITED = set(BODY_RATE_LIMITED_DRIVER_ENDPOINTS)

# `key` is NOT the request attribute it reads like: rate_limiter.py:143 resolves it as
# `frappe.form_dict.get(key, "")`, and app.py:302-314 builds form_dict from the query
# string, so any caller appending `?<key>=anything` lands in a private window per value
# (identity is `<ip>:<value>`, rate_limiter.py:147-148). No key value is safe, so this
# guard demands none. The two identity suites spend the real windows; this budget is the
# ratchet, lowered only — a newly keyed endpoint anywhere in KEY_RATCHET_ENDPOINTS,
# driver portal or not, pushes it over.
LEGACY_FORM_DICT_KEY = "frappe.request.remote_addr"
LEGACY_FORM_DICT_KEY_BUDGET = 0

# The endpoints that carried the same key OUTSIDE the driver portal: four unauthenticated
# guest web-form SUBMITTERS (a forged window there bought unlimited INSERTs, not just
# unlimited reads) plus the Front Desk identifier scan. They are inside the ratchet's
# population rather than beside it, because a budget that only counts driver_portal/
# would sit at zero while the same bypass was re-introduced one directory away — which
# is precisely how these five outlived the pass that closed the other 38.
OFF_PORTAL_KEY_CARRIERS = {
    (
        "habitat/web_form/accommodation_resident_request/accommodation_resident_request.py",
        "submit_resident_request",
    ),
    ("habitat/web_form/arrival_manifest/arrival_manifest.py", "submit_arrival_manifest"),
    ("salis/web_form/transport_request/transport_request.py", "submit_transport_request"),
    ("salis/web_form/vehicle_incident/vehicle_incident.py", "submit_vehicle_incident"),
    ("habitat/api/front_desk.py", "resolve_worker"),
}

NORMAL_DRIVER_WRITERS = DRIVER_WRITERS - TIGHT_DRIVER_WRITERS - BODY_RATE_LIMITED
PER_IP_DRIVER_ENDPOINTS = (
    DRIVER_PORTAL_ENDPOINTS | MIXED_DRIVER_ENDPOINTS
) - BODY_RATE_LIMITED

# The full population the key budget is counted over.
KEY_RATCHET_ENDPOINTS = PER_IP_DRIVER_ENDPOINTS | OFF_PORTAL_KEY_CARRIERS

WORKER_ENDPOINTS = {
    "worker_request_wait": {"allow_guest": True, "methods": ["POST"]},
    "worker_claim_boarded": {"allow_guest": True, "methods": ["POST"]},
    "worker_trip_boarding": {"allow_guest": True},
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _whitelist(node: ast.FunctionDef) -> ast.Call | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "frappe"
            and func.attr == "whitelist"
        ):
            return decorator
    return None


def _literal_keywords(decorator: ast.Call) -> dict[str, object]:
    return {keyword.arg: ast.literal_eval(keyword.value) for keyword in decorator.keywords}


def _rate_limit(node: ast.FunctionDef) -> tuple[int, ast.Call] | None:
    for index, decorator in enumerate(node.decorator_list):
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "rate_limit"
        ):
            return index, decorator
    return None


def _module_endpoints(path: Path) -> dict[str, tuple[ast.FunctionDef, dict[str, object]]]:
    result = {}
    for node in _tree(path).body:
        if isinstance(node, ast.FunctionDef) and (decorator := _whitelist(node)):
            result[node.name] = (node, _literal_keywords(decorator))
    return result


def _endpoint_path(filename: str, name: str) -> Path:
    # Off-portal carriers name themselves by their path relative to the app root; the
    # driver-portal entries are bare basenames, so the two shapes cannot be confused.
    if (filename, name) in OFF_PORTAL_KEY_CARRIERS:
        return ROOT / "apex" / filename
    if (filename, name) in MIXED_DRIVER_ENDPOINTS:
        return ROOT / "apex" / "salis" / "api" / filename
    return DRIVER_PORTAL / filename


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


class TestDriverPortalGuestInventory(unittest.TestCase):
    def test_inventory_covers_every_driver_portal_endpoint(self):
        actual = set()
        for path in sorted(DRIVER_PORTAL.glob("*.py")):
            actual.update((path.name, name) for name in _module_endpoints(path))
        self.assertEqual(actual, DRIVER_PORTAL_ENDPOINTS)

    def test_inventory_covers_every_mixed_boarding_endpoint(self):
        actual = set()
        for path in (BOARDING, BOARDING_FLOW):
            actual.update((path.name, name) for name in _module_endpoints(path))
        self.assertEqual(actual, MIXED_DRIVER_ENDPOINTS | MIXED_WORKER_ENDPOINTS)

    def test_every_driver_endpoint_allows_guest(self):
        for filename, name in sorted(DRIVER_PORTAL_ENDPOINTS | MIXED_DRIVER_ENDPOINTS):
            path = _endpoint_path(filename, name)
            with self.subTest(path=filename, endpoint=name):
                _keywords = _module_endpoints(path)[name][1]
                self.assertIs(_keywords.get("allow_guest"), True)

    def test_every_driver_writer_retains_post_only(self):
        for filename, name in sorted(DRIVER_WRITERS):
            path = _endpoint_path(filename, name)
            with self.subTest(path=filename, endpoint=name):
                self.assertEqual(_module_endpoints(path)[name][1].get("methods"), ["POST"])

    def test_every_driver_endpoint_has_an_explicit_per_ip_rate_limit(self):
        paths = {
            _endpoint_path(filename, name)
            for filename, name in PER_IP_DRIVER_ENDPOINTS
        }
        # Apex's decorator, never the framework's: the framework names the window after
        # the caller's cmd (rate_limiter.py:155), so a module that imports it back gives
        # every endpoint in it one ceiling per dotted path -- and the package publishes a
        # second path for most of these. apex_core/utils/test_submit_rate_limit_identity
        # holds the same line across all 61 metered endpoints.
        for path in paths:
            imports = [
                node
                for node in _tree(path).body
                if isinstance(node, ast.ImportFrom)
                and node.module == "apex.apex_core.utils.rate_limit_identity"
                and any(alias.name == "rate_limit" for alias in node.names)
            ]
            self.assertTrue(imports, path.name)

        for filename, name in sorted(PER_IP_DRIVER_ENDPOINTS):
            path = _endpoint_path(filename, name)
            node = _module_endpoints(path)[name][0]
            with self.subTest(path=filename, endpoint=name):
                rate = _rate_limit(node)
                self.assertIsNotNone(rate)
                rate_index, decorator = rate
                whitelist_index = node.decorator_list.index(_whitelist(node))
                self.assertGreater(rate_index, whitelist_index)

    def test_no_endpoint_lets_the_caller_name_its_own_rate_limit_window(self):
        """The ratchet, over the WHOLE population that ever carried the key.

		Counted across the driver portal AND the off-portal carriers together, because
		a budget scoped to one directory reads zero while the identical bypass lives one
		directory away — which is exactly how the four guest submitters and the Front
		Desk scan outlived the pass that de-keyed the other 38.

		Reading `key` back is not the proof that the window is sound; the two identity
		files spend the real windows for that. This is the ratchet: it may be lowered,
		never raised, so a newly keyed endpoint cannot land quietly.
		"""
        keyed = []
        for filename, name in sorted(KEY_RATCHET_ENDPOINTS):
            path = _endpoint_path(filename, name)
            node = _module_endpoints(path)[name][0]
            with self.subTest(path=filename, endpoint=name):
                rate = _rate_limit(node)
                self.assertIsNotNone(rate)
                keywords = _literal_keywords(rate[1])
                # What makes the window per-IP is `ip_based`, which frappe defaults to
                # True (rate_limiter.py:110) and which alone puts the request IP in the
                # identity (rate_limiter.py:141,147-150). Losing it is the regression to
                # catch here; the key string never carried this property. Matched by
                # IDENTITY against the framework's own `ip_based is True` test
                # (rate_limiter.py:141): a truthy 1 fails that test and silently drops
                # the address, and `== True` would wave it through.
                self.assertIs(keywords.get("ip_based", True), True)
                self.assertEqual(keywords.get("seconds"), 60)
                if "key" in keywords:
                    self.assertEqual(keywords["key"], LEGACY_FORM_DICT_KEY)
                    keyed.append(f"{filename}:{name}")
        self.assertLessEqual(
            len(keyed),
            LEGACY_FORM_DICT_KEY_BUDGET,
            "endpoint(s) let the caller pick their own rate-limit window by appending "
            "a query parameter. Drop the `key` argument; `ip_based` already keys the "
            "window to the request address:\n" + "\n".join(f"  {row}" for row in keyed),
        )

    def test_the_ratchet_population_still_holds_the_off_portal_carriers(self):
        """Non-vacuous: dropping an off-portal carrier out of the set would leave the
		budget at zero while that endpoint was free to be re-keyed."""
        self.assertEqual(len(OFF_PORTAL_KEY_CARRIERS), 5)
        self.assertLessEqual(OFF_PORTAL_KEY_CARRIERS, KEY_RATCHET_ENDPOINTS)
        for filename, name in sorted(OFF_PORTAL_KEY_CARRIERS):
            with self.subTest(path=filename, endpoint=name):
                path = _endpoint_path(filename, name)
                self.assertTrue(path.is_file(), f"{filename} moved — repair the set")
                self.assertIn(name, _module_endpoints(path))

    def test_driver_writer_limits_are_bounded_and_creation_is_tight(self):
        for filename, name in sorted(PER_IP_DRIVER_ENDPOINTS):
            path = _endpoint_path(filename, name)
            node = _module_endpoints(path)[name][0]
            rate = _rate_limit(node)
            with self.subTest(path=filename, endpoint=name):
                self.assertIsNotNone(rate)
                limit = _literal_keywords(rate[1]).get("limit")
                if (filename, name) in TIGHT_DRIVER_WRITERS:
                    self.assertEqual(limit, 10)
                elif (filename, name) in NORMAL_DRIVER_WRITERS:
                    self.assertEqual(limit, 30)
                else:
                    self.assertEqual(limit, 120)

    def test_body_rate_limited_endpoints_still_charge_a_ceiling(self):
        """Leaving the decorator set is a move, not an exit: the body must still charge."""
        self.assertLessEqual(
            BODY_RATE_LIMITED, DRIVER_PORTAL_ENDPOINTS | MIXED_DRIVER_ENDPOINTS
        )
        for endpoint, limiters in sorted(BODY_RATE_LIMITED_DRIVER_ENDPOINTS.items()):
            filename, name = endpoint
            node = _module_endpoints(_endpoint_path(filename, name))[name][0]
            with self.subTest(path=filename, endpoint=name):
                # Body-limited means body-limited: no decorator may creep back and
                # re-introduce the caller-chosen window this endpoint moved to escape.
                self.assertIsNone(_rate_limit(node))
                calls = {
                    _call_name(call)
                    for call in ast.walk(node)
                    if isinstance(call, ast.Call)
                }
                for limiter in limiters:
                    self.assertIn(limiter, calls)

    def test_boarding_pass_read_keeps_its_published_address_ceiling(self):
        """The body limit inherited the decorator's 120-per-minute; nothing looser."""
        constants = {
            target.id: node.value.value
            for node in _tree(BOARDING).body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertEqual(constants.get("PASS_ADDRESS_LIMIT"), 120)
        self.assertEqual(constants.get("PASS_RATE_WINDOW_SECONDS"), 60)

    def test_scan_resolves_actor_before_charging_only_its_quota(self):
        node = _module_endpoints(BOARDING)["scan_boarding_pass"][0]
        self.assertIsNone(_rate_limit(node))

        calls = {
            _call_name(call): call.lineno
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        }
        for required in (
            "_authorize_scan_actor",
            "_enforce_scan_actor_rate_limit",
            "_enforce_scan_unresolved_ip_rate_limit",
            "_verify_token",
        ):
            self.assertIn(required, calls)
        self.assertLess(calls["_authorize_scan_actor"], calls["_verify_token"])
        self.assertLess(calls["_enforce_scan_actor_rate_limit"], calls["_verify_token"])
        self.assertLess(
            calls["_enforce_scan_unresolved_ip_rate_limit"],
            calls["_verify_token"],
        )

    def test_worker_guest_endpoint_decorators_are_unchanged(self):
        actual = {
            name: keywords
            for name, (_node, keywords) in _module_endpoints(BOARDING_FLOW).items()
            if name.startswith("worker_")
        }
        self.assertEqual(actual, WORKER_ENDPOINTS)

    def test_boarding_flow_driver_endpoints_authorize_before_access(self):
        for name in {
            "get_trip_boarding",
            "notify_remaining_passengers",
            "driver_mark_not_boarded",
            "depart_and_finalize",
        }:
            node = _module_endpoints(BOARDING_FLOW)[name][0]
            first_statement = node.body[1] if isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) else node.body[0]
            calls = [call for call in ast.walk(first_statement) if isinstance(call, ast.Call)]
            self.assertTrue(calls, name)
            self.assertEqual(_call_name(calls[0]), "_resolve_trip_for_driver", name)

    def test_boarding_trip_lookup_is_actor_first(self):
        node = next(
            node
            for node in _tree(BOARDING).body
            if isinstance(node, ast.FunctionDef) and node.name == "_resolve_trip"
        )
        calls = [call for call in ast.walk(node) if isinstance(call, ast.Call)]
        credential_line = next(call.lineno for call in calls if _call_name(call) == "_presented_driver")
        staff_line = next(call.lineno for call in calls if _call_name(call) == "_is_staff")
        session_driver_line = next(
            call.lineno for call in calls if _call_name(call) == "_driver_for_user"
        )
        trip_read_line = next(
            call.lineno
            for call in calls
            if isinstance(call.func, ast.Attribute)
            and call.func.attr == "get_value"
            and isinstance(call.func.value, ast.Attribute)
            and call.func.value.attr == "db"
        )
        self.assertLess(credential_line, trip_read_line)
        self.assertLess(staff_line, trip_read_line)
        self.assertLess(session_driver_line, trip_read_line)


class TestDriverPortalBootstrapAndPhotoFlow(unittest.TestCase):
    def test_page_context_uses_the_native_csrf_token(self):
        driver_page = (ROOT / "apex" / "www" / "driver.py").read_text(encoding="utf-8")
        self.assertIn("context.csrf_token = get_csrf_token()", driver_page)

    def test_frontend_never_calls_the_generic_upload_endpoint(self):
        frontend = ROOT / "frontend" / "driver" / "src"
        source = "\n".join(path.read_text(encoding="utf-8") for path in frontend.rglob("*.js"))
        source += "\n" + "\n".join(path.read_text(encoding="utf-8") for path in frontend.rglob("*.vue"))
        self.assertNotIn("/api/method/upload_file", source)
        self.assertNotIn("uploadPrivateFile", source)

    def test_served_driver_bundle_uses_inline_photo_payloads(self):
        driver_html = (ROOT / "apex" / "www" / "driver.html").read_text(encoding="utf-8")
        self.assertIn("/assets/apex/worker_portal/assets/index.js", driver_html)

        assets = {
            name: (SERVED_DRIVER_ASSETS / name).read_text(encoding="utf-8")
            for name in ("upload.js", "Attendance.js", "Tickets.js")
        }
        served = "\n".join(assets.values())
        self.assertNotIn("/api/method/upload_file", served)
        self.assertNotIn("file_url", served)
        self.assertNotRegex(assets["Tickets.js"], r"\battachment\s*:")
        self.assertIn("FileReader", assets["upload.js"])
        for name in ("Attendance.js", "Tickets.js"):
            with self.subTest(asset=name):
                self.assertIn("photo_filename", assets[name])

    def test_photo_helper_returns_inline_photo_payload(self):
        source = (ROOT / "frontend" / "driver" / "src" / "upload.js").read_text(encoding="utf-8")
        self.assertIn("FileReader", source)
        self.assertIn("photo_filename", source)
        self.assertIn("photo:", source)

    def test_support_and_attendance_do_not_accept_uploaded_file_urls(self):
        for filename, endpoint in {
            "support.py": "raise_support_ticket",
            "attendance.py": "driver_check_in",
        }.items():
            node = _module_endpoints(DRIVER_PORTAL / filename)[endpoint][0]
            params = {arg.arg for arg in node.args.args}
            with self.subTest(endpoint=endpoint):
                self.assertNotIn("attachment", params)
                self.assertNotIn("file_url", params)
                self.assertIn("photo", params)
                self.assertIn("photo_filename", params)

    def test_auth_docstrings_describe_credential_first_resolution(self):
        masar = MASAR.read_text(encoding="utf-8")
        notifications = (DRIVER_PORTAL / "notifications.py").read_text(encoding="utf-8")
        self.assertNotIn("Every endpoint resolves the session user", masar)
        self.assertNotIn("Resolves the session user to a Salis Driver", masar)
        self.assertNotIn("whether this user already has", notifications)


if __name__ == "__main__":
    unittest.main()
