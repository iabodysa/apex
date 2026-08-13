from pathlib import Path
from unittest import TestCase

from apex.apex_core.utils.portal_bootstrap import PORTAL_PUBLIC_PATHS


class TestPortalShellContract(TestCase):
    def test_retired_driver_portal_api_surface_is_absent(self):
        app = Path(__file__).parents[1]
        driver_api = app / "salis" / "api" / "driver_portal"

        for module in (
            "attendance.py",
            "boarding.py",
            "clearance.py",
            "fuel.py",
            "home.py",
            "notifications.py",
            "support.py",
        ):
            self.assertFalse((driver_api / module).exists(), module)

        forbidden_symbols = {
            driver_api / "__init__.py": ("def mark_arrived(",),
            driver_api / "execution.py": ("def push_driver_position(",),
            driver_api / "profile.py": (
                "def get_driver_context(",
                "def get_my_vehicle(",
            ),
            app / "salis" / "api" / "fleet_employee.py": (
                "def get_my_recent_trips(",
            ),
            app / "salis" / "api" / "fleet_os.py": (
                "def search_drivers(",
                "def get_status_meta(",
                "def create_handover(",
                "def report_theft(",
                "def bulk_stop_vehicles(",
                "def bulk_workshop_in(",
            ),
        }
        for filename, symbols in forbidden_symbols.items():
            source = filename.read_text()
            for symbol in symbols:
                self.assertNotIn(symbol, source, f"{filename.name}: {symbol}")

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
