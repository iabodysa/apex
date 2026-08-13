from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.apex_core.utils.portal_token_security import DRIVER, WORKER
from apex.salis.api import boarding_flow, web_push


class TestPortalWebPush(TestCase):
    @patch.object(boarding_flow, "_manifest_request_names", return_value=["TR-1", "TR-2"])
    @patch.object(boarding_flow.frappe, "get_all")
    @patch.object(boarding_flow.frappe.db, "get_value")
    def test_arrival_targets_only_workers_at_that_stop(
        self, get_value, get_all, _requests
    ):
        get_value.return_value = frappe._dict(
            stop_name="بوابة أ",
            accommodation_building="BLD-1",
        )
        get_all.side_effect = [
            [
                frappe._dict(name="TR-1", accommodation_building="BLD-1"),
                frappe._dict(name="TR-2", accommodation_building="BLD-2"),
            ],
            [
                frappe._dict(parent="TR-1", employee="EMP-1", pickup_point=""),
                frappe._dict(parent="TR-2", employee="EMP-2", pickup_point="بوابة أ"),
                frappe._dict(parent="TR-2", employee="EMP-3", pickup_point="بوابة ب"),
            ],
        ]

        self.assertEqual(
            boarding_flow._manifest_employees_for_stop("DT-1", "STOP-1"),
            ["EMP-1", "EMP-2"],
        )

    @patch.object(web_push, "enqueue_to_subject")
    def test_boarding_events_notify_only_the_affected_portal_audience(self, enqueue):
        web_push.enqueue_boarding_event(
            "wait_request",
            "DT-1",
            driver="DRV-1",
            employees=["EMP-1"],
        )
        enqueue.assert_called_once_with(
            DRIVER,
            "DRV-1",
            "طلب انتظار",
            "أحد الركاب طلب منك الانتظار قبل المغادرة.",
            "/driver/#/route/DT-1",
        )

        enqueue.reset_mock()
        web_push.enqueue_boarding_event(
            "boarding_arrived",
            "DT-1",
            driver="DRV-1",
            employees=["EMP-1", "EMP-1", "EMP-2"],
        )
        self.assertEqual(
            [call.args[:2] for call in enqueue.call_args_list],
            [(WORKER, "EMP-1"), (WORKER, "EMP-2")],
        )
        self.assertTrue(all(call.args[4] == "/masar/#/transport" for call in enqueue.call_args_list))

    @patch.object(web_push, "_deliver", return_value=True)
    @patch.object(web_push, "_active_subscriptions")
    @patch.object(web_push, "_vapid_config")
    def test_send_to_subject_fans_out_without_exposing_subject_in_payload(
        self, config, subscriptions, deliver
    ):
        config.return_value = {"public_key": "public", "private_key": "private", "subject": "mailto:ops@example.com"}
        subscriptions.return_value = [
            {"name": "SUB-1", "endpoint": "https://web.push.apple.com/a", "p256dh": "key"},
            {"name": "SUB-2", "endpoint": "https://web.push.apple.com/b", "p256dh": "key"},
        ]

        result = web_push.send_to_subject(
            WORKER,
            "EMP-PRIVATE",
            "وصلت الحافلة",
            "السائق عند نقطة تجمعك الآن.",
            "/masar/#/transport",
        )

        self.assertEqual(result, {"sent": 2, "devices": 2})
        for call in deliver.call_args_list:
            self.assertNotIn("EMP-PRIVATE", call.args[2])
