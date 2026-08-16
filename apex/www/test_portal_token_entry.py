from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import driver, masar


_MISSING = object()

# Every thread-local a case in this file replaces. `site` and `conf` are the dangerous
# pair: a render case sets site to "apex.localhost" while the run is on ci.localhost, and
# without a restore every module that sorts after this one inherits the wrong site.
_REPLACED_LOCALS = ("form_dict", "flags", "cookie_manager", "request", "site", "conf")


class PortalEntryTestCase(FrappeTestCase):
    def setUp(self):
        # Borrowed, so handed back: capture whatever frappe.local held before this case
        # touched it and put it back afterwards, deleting the attribute again when it did
        # not exist at all. FrappeTestCase's own class cleanup only restores `flags`.
        for name in _REPLACED_LOCALS:
            self.addCleanup(self._restore_local, name, getattr(frappe.local, name, _MISSING))

        frappe.local.form_dict = frappe._dict()
        frappe.local.flags = frappe._dict()
        frappe.local.cookie_manager = MagicMock()

    @staticmethod
    def _restore_local(name, value):
        if value is _MISSING:
            try:
                delattr(frappe.local, name)
            except AttributeError:
                pass
        else:
            setattr(frappe.local, name, value)

    def _context(self):
        return SimpleNamespace()


class TestMasarTokenEntry(PortalEntryTestCase):
    def _render_context_with_cookie(self, token):
        frappe.local.form_dict = frappe._dict()
        frappe.local.request = SimpleNamespace(cookies={masar.MASAR_TOKEN_COOKIE: token})
        frappe.local.site = "apex.localhost"
        frappe.local.conf = frappe._dict(
            socketio_port=9000,
            developer_mode=0,
            encryption_key="test-key",
        )
        with (
            patch.object(masar, "render_in_arabic"),
            patch.object(masar, "_resolve_token_subject", return_value="EMP-DEMO" if token == "live-worker-token" else None),
            patch(
                "apex.apex_core.utils.portal_bootstrap.get_csrf_token",
                return_value="csrf",
            ),
        ):
            return masar.get_context(self._context())

    @patch.object(masar, "_token_resolves", return_value=True)
    def test_live_query_token_is_cookied_then_redirected_to_canonical_path(
        self, resolves
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

    @patch.object(masar, "_token_resolves", return_value=False)
    def test_invalid_query_token_is_not_cookied_and_is_stripped(self, resolves):
        frappe.local.form_dict = frappe._dict(w="dead-worker-token")

        with self.assertRaises(frappe.Redirect):
            masar.get_context(self._context())

        resolves.assert_called_once_with("dead-worker-token")
        self.assertEqual(frappe.local.flags.redirect_location, "/masar/")
        frappe.local.cookie_manager.set_cookie.assert_not_called()
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            masar.MASAR_TOKEN_COOKIE
        )

    @patch.object(masar, "_token_resolves")
    def test_malformed_or_empty_query_is_always_stripped(self, resolves):
        for raw in ("bad token!", ""):
            with self.subTest(raw=raw):
                frappe.local.form_dict = frappe._dict(w=raw)
                frappe.local.flags = frappe._dict()
                with self.assertRaises(frappe.Redirect):
                    masar.get_context(self._context())
                self.assertEqual(frappe.local.flags.redirect_location, "/masar/")
        resolves.assert_not_called()

    def test_live_cookie_bootstraps_authenticated_shell(self):
        context = self._render_context_with_cookie("live-worker-token")

        self.assertEqual(context.boot["apex_portal"]["entry"], "worker")
        self.assertIn("worker.home", context.boot["apex_portal"]["capabilities"])
        frappe.local.cookie_manager.delete_cookie.assert_not_called()

    def test_dead_cookie_is_deleted_before_guest_shell_render(self):
        context = self._render_context_with_cookie("dead-worker-token")

        self.assertEqual(context.boot["apex_portal"]["capabilities"], [])
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            masar.MASAR_TOKEN_COOKIE
        )

    def test_missing_cookie_bootstraps_guest_shell_without_resolution(self):
        context = self._render_context_with_cookie("")

        self.assertEqual(context.boot["apex_portal"]["capabilities"], [])
        frappe.local.cookie_manager.delete_cookie.assert_not_called()


class TestDriverTokenEntry(PortalEntryTestCase):
    @patch.object(driver, "_token_resolves", return_value=True)
    def test_live_query_token_is_cookied_then_redirected_to_canonical_path(
        self, resolves
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

    @patch.object(driver, "_token_resolves", return_value=False)
    def test_invalid_query_token_is_not_cookied_and_is_stripped(self, resolves):
        frappe.local.form_dict = frappe._dict(d="dead-driver-token")

        with self.assertRaises(frappe.Redirect):
            driver.get_context(self._context())

        resolves.assert_called_once_with("dead-driver-token")
        self.assertEqual(frappe.local.flags.redirect_location, "/driver/")
        frappe.local.cookie_manager.set_cookie.assert_not_called()
        frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
            driver.DRIVER_TOKEN_COOKIE
        )

    @patch.object(driver, "_token_resolves")
    def test_malformed_or_empty_query_is_stripped_without_a_token_cookie(
        self, resolves
    ):
        for raw in ("bad token!", ""):
            with self.subTest(raw=raw):
                frappe.local.form_dict = frappe._dict(d=raw)
                frappe.local.flags = frappe._dict()
                frappe.local.cookie_manager.reset_mock()
                with self.assertRaises(frappe.Redirect):
                    driver.get_context(self._context())
                self.assertEqual(frappe.local.flags.redirect_location, "/driver/")
                frappe.local.cookie_manager.set_cookie.assert_not_called()
                frappe.local.cookie_manager.delete_cookie.assert_called_once_with(
                    driver.DRIVER_TOKEN_COOKIE
                )
        resolves.assert_not_called()

    @patch.object(driver, "render_in_arabic")
    @patch.object(driver, "_request_token_cookie", return_value="")
    @patch("apex.apex_core.utils.portal_bootstrap.get_csrf_token", return_value="csrf")
    def test_render_without_a_token_cookie_publishes_no_capabilities(
        self, _csrf, _cookie, _arabic
    ):
        frappe.local.form_dict = frappe._dict()
        frappe.local.site = "apex.localhost"
        frappe.local.conf = frappe._dict(
            socketio_port=9000,
            developer_mode=0,
            encryption_key="test-key",
        )

        context = driver.get_context(self._context())

        self.assertEqual(context.boot["apex_portal"]["capabilities"], [])
        self.assertTrue(context.csrf_token, "an unauthenticated render still needs a CSRF token")
        frappe.local.cookie_manager.delete_cookie.assert_not_called()
