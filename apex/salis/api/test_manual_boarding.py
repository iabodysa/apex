from unittest import TestCase
from unittest.mock import MagicMock, patch

from apex.salis.api import manual_boarding


class TestManualBoarding(TestCase):
    @patch.object(manual_boarding, "_log_attempt", return_value="SCAN-1")
    @patch("apex.salis.api.boarding_flow.mark_boarded")
    @patch("apex.salis.api.driver_portal._require_enabled")
    @patch("apex.salis.api.boarding._already_boarded", return_value=False)
    @patch("apex.salis.api.boarding._get_or_create_log")
    @patch("apex.salis.api.boarding._trip_manifest_workers", return_value={"EMP-1"})
    @patch(
        "apex.salis.api.boarding._resolve_trip",
        return_value={"driver": "DRV-1", "transport_request": "TR-1"},
    )
    @patch.object(manual_boarding.frappe.db, "get_value", return_value="DT-1")
    def test_manual_fallback_reuses_the_canonical_boarding_log(
        self,
        _lock,
        _trip,
        _manifest,
        get_log,
        _already,
        _enabled,
        mark_boarded,
        _audit,
    ):
        log = MagicMock(name="log")
        log.name = "LOG-1"
        log.boarded_count = 1
        get_log.return_value = log

        result = manual_boarding.board_worker("DT-1", "EMP-1")

        log.append.assert_called_once()
        self.assertEqual(log.append.call_args.args[0], "boarding_events")
        self.assertEqual(log.append.call_args.args[1]["method"], "Manual")
        mark_boarded.assert_called_once_with("DT-1", "EMP-1", source="Manual")
        self.assertEqual(result["result"], "Valid")
