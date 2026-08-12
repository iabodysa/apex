from unittest import TestCase
from unittest.mock import patch

from apex.salis.api import masar


class TestMasarWorkerHome(TestCase):
    @patch.object(masar, "_resolve_worker", return_value="EMP-1")
    @patch.object(masar, "get_worker_context", return_value={"employee": {"name": "EMP-1"}, "documents": []})
    @patch.object(masar, "get_worker_transport", return_value={"upcoming": [], "history": []})
    @patch.object(masar, "get_worker_accommodation", return_value={"assignment": {"name": "HA-1"}, "bed": None})
    @patch.object(masar, "get_worker_custody", return_value={"items": []})
    @patch.object(masar, "list_worker_requests", return_value=[])
    def test_home_is_one_bounded_worker_read_model(
        self, requests, custody, accommodation, transport, profile, _worker
    ):
        result = masar.get_worker_home()

        self.assertEqual(result["profile"], profile.return_value)
        self.assertEqual(result["accommodation"], accommodation.return_value)
        self.assertEqual(result["custody"], custody.return_value)
        self.assertEqual(result["transport"], transport.return_value)
        self.assertEqual(result["requests"], requests.return_value)
