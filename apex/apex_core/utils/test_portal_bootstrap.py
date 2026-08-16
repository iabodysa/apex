from unittest import TestCase

import frappe

from apex.apex_core.utils.portal_bootstrap import (
    build_portal_bootstrap,
    build_portal_shell_meta,
    opaque_subject_scope,
    publish_portal_context,
)


class TestPortalBootstrap(TestCase):
    def test_builds_only_the_public_non_secret_contract(self):
        bootstrap = build_portal_bootstrap(
            entry="worker",
            public_path="/masar/",
            initial_route="/home",
            capabilities=["worker.trip.read", "worker.trip.read", "worker.request.create"],
            site_name="apex.localhost",
            socketio_port=9000,
            async_enabled=True,
            language="ar",
            subject_scope="subject_3f189c11",
        )

        self.assertEqual(
            bootstrap,
            {
                "entry": "worker",
                "public_path": "/masar/",
                "initial_route": "/home",
                "capabilities": ["worker.request.create", "worker.trip.read"],
                "site_name": "apex.localhost",
                "socketio_port": 9000,
                "async_enabled": True,
                "language": "ar",
                "subject_scope": "subject_3f189c11",
            },
        )
        for forbidden in ("token", "cookie", "password", "api_key", "user", "name"):
            self.assertNotIn(forbidden, bootstrap)

    def test_rejects_unknown_entry_path_pair(self):
        with self.assertRaises(ValueError):
            build_portal_bootstrap(
                entry="worker",
                public_path="/driver/",
                initial_route="/home",
                capabilities=[],
                site_name="apex.localhost",
                socketio_port=9000,
                async_enabled=False,
                language="ar",
                subject_scope="subject_3f189c11",
            )

    def test_rejects_a_raw_user_identity_as_subject_scope(self):
        with self.assertRaises(ValueError):
            build_portal_bootstrap(
                entry="worker",
                public_path="/masar/",
                initial_route="/home",
                capabilities=[],
                site_name="apex.localhost",
                socketio_port=9000,
                async_enabled=False,
                language="ar",
                subject_scope="worker@example.com",
            )

    def test_shell_metadata_contains_no_authorization_state(self):
        meta = build_portal_shell_meta(entry="driver", public_path="/driver/")

        self.assertEqual(
            meta,
            {
                "title": "أبكس | السائق",
                "canonical_path": "/driver/",
                "manifest_url": "/assets/apex/apex_portal/manifests/driver.webmanifest",
                "apple_icon_url": (
                    "/assets/apex/apex_portal/icons/driver-apple-touch-icon-180.png"
                ),
                "theme_color": "#00844E",
                "service_worker_url": "/driver-sw.min.js",
                "service_worker_scope": "/driver/",
            },
        )
        self.assertNotIn("capabilities", meta)
        self.assertNotIn("subject_scope", meta)

    def test_non_pwa_entry_has_no_manifest_or_worker(self):
        meta = build_portal_shell_meta(entry="housing", public_path="/safety")

        self.assertIsNone(meta["manifest_url"])
        self.assertIsNone(meta["apple_icon_url"])
        self.assertIsNone(meta["service_worker_url"])
        self.assertIsNone(meta["service_worker_scope"])

    def test_subject_scope_is_stable_and_does_not_expose_identity(self):
        first = opaque_subject_scope(entry="worker", subject="EMP-0001")
        second = opaque_subject_scope(entry="worker", subject="EMP-0001")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^scope_[0-9a-f]{24}$")
        self.assertNotIn("EMP-0001", first)

    def test_publishes_bootstrap_and_shell_as_separate_contracts(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        context = SimpleNamespace()
        with patch(
            "apex.apex_core.utils.portal_bootstrap.frappe.get_site_config",
            return_value={
                "socketio_port": 9001,
                "disable_async": 0,
                "encryption_key": "test-key",
            },
        ), patch(
            "apex.apex_core.utils.portal_bootstrap.get_csrf_token",
            return_value="csrf-test",
        ):
            publish_portal_context(
                context,
                entry="housing",
                public_path="/housing",
                initial_route="/overview",
                capabilities=["estate_read"],
                subject="Administrator",
            )

        self.assertEqual(context.csrf_token, "csrf-test")
        self.assertEqual(context.shell_meta["canonical_path"], "/housing")
        self.assertEqual(context.boot["apex_portal"]["entry"], "housing")
        self.assertEqual(context.boot["apex_portal"]["capabilities"], ["estate_read"])
        self.assertNotIn("Administrator", str(context.boot))

    def test_publishes_the_arabic_dictionary_as_its_own_contract(self):
        """The portal is a standalone document, so it receives no bootinfo and no
        ``frappe._messages`` — this contract is the only way ar.csv reaches the page.

        The session language is pinned to ``ar`` rather than inherited, for two reasons. The
        suite runs in English, so an inherited language would look for an ``en.csv`` apex
        does not ship and hand back ``{}`` — a pass that proves nothing. And ``{}`` IS the
        correct answer for an English session, so the assertion has to name the language it
        is grading rather than assume one.

        Asserted on a non-empty dictionary rather than on the key's presence, because an
        empty one would satisfy a presence check and ship an untranslated portal. Asserted
        as a SEPARATE attribute rather than a member of ``boot``: ``core/session.js``
        refuses any unknown key inside the bootstrap dict, so folding the dictionary in
        there would throw in the browser.
        """
        from types import SimpleNamespace
        from unittest.mock import patch

        self.addCleanup(setattr, frappe.local, "lang", getattr(frappe.local, "lang", "en"))
        frappe.local.lang = "ar"
        context = SimpleNamespace()
        with patch(
            "apex.apex_core.utils.portal_bootstrap.frappe.get_site_config",
            return_value={
                "socketio_port": 9001,
                "disable_async": 0,
                "encryption_key": "test-key",
            },
        ), patch(
            "apex.apex_core.utils.portal_bootstrap.get_csrf_token",
            return_value="csrf-test",
        ):
            publish_portal_context(
                context,
                entry="housing",
                public_path="/housing",
                initial_route="/overview",
                capabilities=["estate_read"],
                subject="Administrator",
            )

        self.assertIsInstance(context.portal_messages, dict)
        self.assertTrue(context.portal_messages, "the Arabic dictionary reached the page empty")
        self.assertNotIn(
            "portal_messages",
            context.boot["apex_portal"],
            "the dictionary must stay its own contract — session.js refuses unknown boot keys",
        )
