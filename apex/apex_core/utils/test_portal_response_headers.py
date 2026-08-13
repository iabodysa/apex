from unittest import TestCase

from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request, Response

from apex import hooks
from apex.apex_core.utils.portal_response_headers import (
    apply_portal_response_headers,
)


class TestPortalResponseHeaders(TestCase):
    def _apply(self, path, *, vary=None):
        request = Request(EnvironBuilder(path=path).get_environ())
        response = Response()
        if vary:
            for value in vary:
                response.headers.add("Vary", value)
        apply_portal_response_headers(request=request, response=response)
        return response.headers

    def test_policy_is_registered_as_the_single_apex_after_request_hook(self):
        self.assertEqual(
            hooks.after_request,
            [
                "apex.apex_core.utils.portal_response_headers."
                "apply_portal_response_headers"
            ],
        )

    def test_all_seven_portal_pages_are_private_and_not_stored(self):
        for path in (
            "/masar/",
            "/driver/",
            "/masar-supervisor",
            "/fleet",
            "/fleet-os",
            "/housing",
            "/safety",
        ):
            with self.subTest(path=path):
                headers = self._apply(path)
                self.assertEqual(
                    headers["Cache-Control"], "no-store, private, max-age=0"
                )
                self.assertEqual(headers["Pragma"], "no-cache")
                self.assertEqual(headers["Vary"], "Cookie")

    def test_personal_api_namespaces_are_private_and_not_stored(self):
        for path in (
            "/api/method/apex.salis.api.masar.get_worker_home",
            "/api/method/apex.salis.api.masar_worker.get_worker_context",
            "/api/method/apex.salis.api.driver_portal.get_driver_profile",
            "/api/method/apex.salis.api.boarding.scan_boarding_pass",
            "/api/method/apex.salis.api.boarding_flow.worker_trip_boarding",
        ):
            with self.subTest(path=path):
                headers = self._apply(path)
                self.assertEqual(
                    headers["Cache-Control"], "no-store, private, max-age=0"
                )
                self.assertEqual(headers["Pragma"], "no-cache")

    def test_authenticated_portal_and_credential_issuance_apis_are_not_stored(self):
        for path in (
            "/api/method/apex.habitat.api.front_desk.get_building_grid",
            "/api/method/apex.salis.api.fleet_employee.get_context",
            "/api/method/apex.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
        ):
            with self.subTest(path=path):
                headers = self._apply(path)
                self.assertEqual(
                    headers["Cache-Control"], "no-store, private, max-age=0"
                )
                self.assertEqual(headers["Vary"], "Cookie")

    def test_vary_cookie_is_appended_once_case_insensitively(self):
        headers = self._apply(
            "/housing", vary=["Accept-Encoding", "Origin, cookie"]
        )

        self.assertEqual(headers.getlist("Vary"), ["Accept-Encoding, Origin, cookie"])

    def test_worker_scripts_receive_only_their_exact_allowed_scope(self):
        expected = {
            "/masar-sw.min.js": "/masar/",
            "/driver-sw.min.js": "/driver/",
        }
        for path, scope in expected.items():
            with self.subTest(path=path):
                headers = self._apply(path)
                self.assertEqual(headers["Service-Worker-Allowed"], scope)
                self.assertEqual(
                    headers["Cache-Control"], "no-store, private, max-age=0"
                )

    def test_unrelated_pages_apis_and_similar_paths_are_untouched(self):
        for path in (
            "/app",
            "/login",
            "/housing-report",
            "/api/method/frappe.client.get_list",
            "/api/method/apex.apex_core.setup.demo.get_status",
            "/housing//",
            "/masar-sw.min.js.map",
        ):
            with self.subTest(path=path):
                headers = self._apply(path, vary=["Accept-Encoding"])
                self.assertNotIn("Cache-Control", headers)
                self.assertNotIn("Pragma", headers)
                self.assertNotIn("Service-Worker-Allowed", headers)
                self.assertEqual(headers.getlist("Vary"), ["Accept-Encoding"])
