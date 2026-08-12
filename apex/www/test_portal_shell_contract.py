from pathlib import Path
from unittest import TestCase

from apex.apex_core.utils.portal_bootstrap import PORTAL_PUBLIC_PATHS


class TestPortalShellContract(TestCase):
    def test_all_seven_adapters_use_only_the_generated_shell(self):
        www = Path(__file__).parent
        for filename in (
            "masar.html",
            "driver.html",
            "masar-supervisor.html",
            "fleet.html",
            "fleet-os.html",
            "housing.html",
            "safety.html",
        ):
            source = (www / filename).read_text().strip()
            self.assertEqual(
                source,
                '{%- include "apex/templates/includes/apex_portal_app.html" -%}',
                filename,
            )

    def test_public_path_contract_has_six_contexts_and_seven_paths(self):
        self.assertEqual(len(PORTAL_PUBLIC_PATHS), 6)
        self.assertEqual(sum(map(len, PORTAL_PUBLIC_PATHS.values())), 7)

    def test_controllers_do_not_publish_legacy_or_personal_boot_fields(self):
        www = Path(__file__).parent
        forbidden = (
            "context.user_full_name",
            "context.masar_has_token",
            "context.driver_has_token",
            "context.portal_sections",
            "context.portal_capabilities",
            "context.fleet_caps",
        )
        for filename in (
            "masar.py",
            "driver.py",
            "masar_supervisor.py",
            "fleet.py",
            "fleet_os.py",
            "housing.py",
            "safety.py",
        ):
            source = (www / filename).read_text()
            for marker in forbidden:
                self.assertNotIn(marker, source, f"{filename}: {marker}")
