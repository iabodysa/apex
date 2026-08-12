from unittest import TestCase

from apex.apex_core.utils.portal_bootstrap import (
    build_portal_bootstrap,
    build_portal_shell_meta,
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
                "manifest_url": "/assets/apex/worker_portal/driver.webmanifest",
                "apple_icon_url": (
                    "/assets/apex/worker_portal/icons/driver-apple-touch-icon-180.png"
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
