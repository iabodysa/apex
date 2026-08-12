from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import driver, masar


class PortalEntryTestCase(FrappeTestCase):
    def setUp(self):
        frappe.local.form_dict = frappe._dict()
        frappe.local.flags = frappe._dict()
        frappe.local.cookie_manager = MagicMock()

    def _context(self):
        return SimpleNamespace()


class TestMasarTokenEntry(PortalEntryTestCase):
    def _render_context_with_cookie(self, token):
        frappe.local.form_dict = frappe._dict()
        frappe.local.request = SimpleNamespace(cookies={masar.MASAR_TOKEN_COOKIE: token})
        frappe.local.site = "apex.localhost"
        frappe.local.conf = frappe._dict(socketio_port=9000, developer_mode=0)
        with (
            patch.object(masar, "get_csrf_token", return_value="csrf"),
            patch.object(masar, "render_in_arabic"),
            patch.object(masar, "apply_portal_appearance"),
        ):
            return masar.get_context(self._context())

    @patch.object(masar, "get_csrf_token", return_value="csrf")
    @patch.object(masar, "_token_resolves", return_value=True)
    def test_live_query_token_is_cookied_then_redirected_to_canonical_path(
        self, resolves, _csrf
    ):
        frappe.local.form_dict = frappe._dict(w="live-worker-token")

        with self.assertRaises(frappe.Redirect):
            masar.get_context(self._context())

        resolves.assert_called_once_with("live-worker-token")
        self.assertEqual(frappe.local.flags.redirect_location, "/masar/")
        frappe.local.cookie_manager.set_cookie.assert_called_once_with(
            masar.MASAR_TOKEN_COOKIE,
            "live-worker-token",
            httponly=True,
            samesite="Lax",
            max_age=masar._COOKIE_MAX_AGE_SECONDS,
        )

    @patch.object(masar, "get_csrf_token", return_value="csrf")
    @patch.object(masar, "_token_resolves", return_value=False)
    def test_invalid_query_token_is_not_cookied_and_is_stripped(self, resolves, _csrf):
        frappe.local.form_dict = frappe._dict(w="dead-worker-token")

        with self.assertRaises(frappe.Redirect):
            masar.get_context(self._context())

        resolves.assert_called_once_with("dead-worker-token")
        self.assertEqual(frappe.local.flags.redirect_location, "/masar/")
        frappe.local.cookie_manager.set_cookie.assert_not_called()
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            masar.MASAR_TOKEN_COOKIE
        )

    @patch.object(masar, "get_csrf_token", return_value="csrf")
    @patch.object(masar, "_token_resolves")
    def test_malformed_or_empty_query_is_always_stripped(self, resolves, _csrf):
        for raw in ("bad token!", ""):
            with self.subTest(raw=raw):
                frappe.local.form_dict = frappe._dict(w=raw)
                frappe.local.flags = frappe._dict()
                with self.assertRaises(frappe.Redirect):
                    masar.get_context(self._context())
                self.assertEqual(frappe.local.flags.redirect_location, "/masar/")
        resolves.assert_not_called()

    @patch.object(masar, "_token_resolves", return_value=True)
    def test_live_cookie_bootstraps_authenticated_shell(self, resolves):
        context = self._render_context_with_cookie("live-worker-token")

        resolves.assert_called_once_with("live-worker-token")
        self.assertTrue(context.masar_has_token)
        frappe.local.cookie_manager.delete_cookie.assert_not_called()

    @patch.object(masar, "_token_resolves", return_value=False)
    def test_dead_cookie_is_deleted_before_guest_shell_render(self, resolves):
        context = self._render_context_with_cookie("dead-worker-token")

        resolves.assert_called_once_with("dead-worker-token")
        self.assertFalse(context.masar_has_token)
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            masar.MASAR_TOKEN_COOKIE
        )

    @patch.object(masar, "_token_resolves")
    def test_missing_cookie_bootstraps_guest_shell_without_resolution(self, resolves):
        context = self._render_context_with_cookie("")

        resolves.assert_not_called()
        self.assertFalse(context.masar_has_token)
        frappe.local.cookie_manager.delete_cookie.assert_not_called()


class TestDriverTokenEntry(PortalEntryTestCase):
    @patch.object(driver, "get_csrf_token", return_value="csrf")
    @patch.object(driver, "_token_resolves", return_value=True)
    def test_live_query_token_is_cookied_then_redirected_to_canonical_path(
        self, resolves, _csrf
    ):
        frappe.local.form_dict = frappe._dict(d="live-driver-token")

        with self.assertRaises(frappe.Redirect):
            driver.get_context(self._context())

        resolves.assert_called_once_with("live-driver-token")
        self.assertEqual(frappe.local.flags.redirect_location, "/driver/")
        frappe.local.cookie_manager.set_cookie.assert_called_once_with(
            driver.DRIVER_TOKEN_COOKIE,
            "live-driver-token",
            httponly=True,
            samesite="Lax",
            max_age=driver._COOKIE_MAX_AGE_SECONDS,
        )

    @patch.object(driver, "get_csrf_token", return_value="csrf")
    @patch.object(driver, "_token_resolves", return_value=False)
    def test_invalid_query_token_is_not_cookied_and_is_stripped(self, resolves, _csrf):
        frappe.local.form_dict = frappe._dict(d="dead-driver-token")

        with self.assertRaises(frappe.Redirect):
            driver.get_context(self._context())

        resolves.assert_called_once_with("dead-driver-token")
        self.assertEqual(frappe.local.flags.redirect_location, "/driver/")
        frappe.local.cookie_manager.set_cookie.assert_called_once_with(
            driver.DRIVER_LINK_DEAD_COOKIE,
            "1",
            httponly=True,
            samesite="Lax",
            max_age=driver._LINK_DEAD_MAX_AGE_SECONDS,
        )
        token_cookie_calls = [
            call
            for call in frappe.local.cookie_manager.set_cookie.call_args_list
            if call.args and call.args[0] == driver.DRIVER_TOKEN_COOKIE
        ]
        self.assertEqual(token_cookie_calls, [])
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            driver.DRIVER_TOKEN_COOKIE
        )

    @patch.object(driver, "get_csrf_token", return_value="csrf")
    @patch.object(driver, "_token_resolves")
    def test_malformed_or_empty_query_is_marked_dead_and_stripped(
        self, resolves, _csrf
    ):
        for raw in ("bad token!", ""):
            with self.subTest(raw=raw):
                frappe.local.form_dict = frappe._dict(d=raw)
                frappe.local.flags = frappe._dict()
                frappe.local.cookie_manager.reset_mock()
                with self.assertRaises(frappe.Redirect):
                    driver.get_context(self._context())
                self.assertEqual(frappe.local.flags.redirect_location, "/driver/")
                frappe.local.cookie_manager.set_cookie.assert_called_once_with(
                    driver.DRIVER_LINK_DEAD_COOKIE,
                    "1",
                    httponly=True,
                    samesite="Lax",
                    max_age=driver._LINK_DEAD_MAX_AGE_SECONDS,
                )
        resolves.assert_not_called()

    @patch.object(driver, "apply_portal_appearance")
    @patch.object(driver, "render_in_arabic")
    @patch.object(driver, "get_csrf_token", return_value="csrf")
    @patch.object(driver, "_request_token_cookie", return_value="")
    def test_dead_link_marker_survives_redirect_for_one_render_without_secret(
        self, _cookie, _csrf, _arabic, _appearance
    ):
        frappe.local.request = SimpleNamespace(
            cookies={driver.DRIVER_LINK_DEAD_COOKIE: "1"}
        )
        frappe.local.form_dict = frappe._dict()
        frappe.local.site = "apex.localhost"
        frappe.local.conf = frappe._dict(socketio_port=9000, developer_mode=0)

        context = driver.get_context(self._context())

        self.assertTrue(context.driver_link_dead)
        self.assertFalse(context.driver_has_token)
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            driver.DRIVER_LINK_DEAD_COOKIE
        )
