# Copyright (c) 2026, afmcoltd
"""Regression: what the fleet watchers put in front of an operator is a translated
whole sentence.

``_queue_document`` writes its ``message`` to ToDo.description and to a document
comment — both operator-facing surfaces. The three watchers built that text as raw
English f-strings carrying the internal job name, and the compliance watcher spliced
in a bare "expired on" / "expires on" fragment, which a translator receives with no
tense, no subject and no way to know where it lands in the target word order.

The log line is a different audience and keeps the job name: these tests assert on
what reaches ``_queue_document``, not on what reaches ``logger``.

Pure unit tests: the module's ``frappe`` handle and ``frappe.utils`` date helpers
are replaced, so no site and no tables.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from apex.salis.tasks import vehicle


JOB_NAMES = (
    "idle_vehicle_watch",
    "vehicle_compliance_expiry_watch",
    "vehicle_utilization_summary",
)

# The bare fragments the compliance watcher's msgids must never carry on their own.
FRAGMENTS = ("expired on", "expires on")


class _Column:
    """A query-builder column stand-in that answers every comparison.

    A bare ``MagicMock`` returns ``NotImplemented`` from ``__ge__``/``__le__``, so
    ``DT.trip_date >= cutoff`` raises TypeError, the watcher's aggregate ``except``
    swallows it and the loop under test never runs. That failure looked exactly like
    a passing watcher that queued nothing.
    """

    def __getattr__(self, name):
        return _Column()

    def __call__(self, *args, **kwargs):
        return _Column()

    __ge__ = __le__ = __gt__ = __lt__ = __eq__ = __ne__ = __sub__ = __call__

    def __hash__(self):
        return id(self)

    def __iter__(self):
        """``.run()`` lands here: no vehicle has a recent trip, so every row is queued."""
        return iter(())


class _Recorder:
    """Stands in for ``frappe._``: records every msgid and returns it unchanged."""

    def __init__(self):
        self.msgids = []

    def __call__(self, message):
        self.msgids.append(message)
        return message


def _run_watcher(func, rows, *, single_page=True, **extra_patches):
    """Drive one watcher over ``rows`` and return (queued_messages, translated_msgids).

    ``frappe.get_all`` answers the first page with ``rows`` and every later page with
    ``[]``, which is what stops the watcher's batching loop.
    """
    pages = [rows, []] if single_page else list(rows)
    translate = _Recorder()
    queued = []

    mock_frappe = mock.MagicMock()
    mock_frappe.get_all.side_effect = pages
    mock_frappe.qb.DocType.return_value = _Column()
    mock_frappe.qb.from_.return_value = _Column()

    with mock.patch.object(vehicle, "frappe", mock_frappe), mock.patch.object(
        vehicle, "_", translate
    ), mock.patch.object(
        vehicle,
        "_queue_document",
        side_effect=lambda doctype, name, severity, message, **kw: queued.append(message),
    ), mock.patch.object(
        vehicle, "_settings_int", return_value=7
    ), mock.patch.multiple(
        "frappe.utils",
        today=mock.Mock(return_value="2026-08-15"),
        add_days=mock.Mock(return_value="2026-08-08"),
        getdate=mock.Mock(side_effect=lambda value: value),
        **extra_patches,
    ):
        func()

    return queued, translate.msgids


class TestVehicleWatchOperatorText(unittest.TestCase):
    def _assert_operator_sentence(self, queued):
        self.assertTrue(queued, "the watcher queued nothing to assert on")
        for message in queued:
            for job in JOB_NAMES:
                self.assertNotIn(
                    job,
                    message,
                    f"the operator is shown the internal job name: {message!r}",
                )

    def test_idle_watch_queues_a_translated_sentence(self):
        queued, msgids = _run_watcher(
            vehicle.idle_vehicle_watch, [SimpleNamespace(name="VEH-1")]
        )
        self._assert_operator_sentence(queued)
        self.assertIn(
            "Vehicle {0} has had no dispatch trip in the last {1} days.", msgids
        )

    def test_utilisation_summary_queues_a_translated_sentence(self):
        queued, msgids = _run_watcher(
            vehicle.vehicle_utilization_summary,
            [SimpleNamespace(name="VEH-1")],
        )
        self._assert_operator_sentence(queued)
        self.assertIn("Vehicle {0} logged no dispatch trips in the last 7 days.", msgids)

    def test_compliance_watch_translates_two_whole_sentences_not_a_fragment(self):
        """Expired and expiring are separate msgids, and neither is a bare fragment."""
        seen = {}
        for label, expiry in (("expired", "2026-08-01"), ("expiring", "2026-08-30")):
            row = SimpleNamespace(
                parent="VEH-1", compliance_type="Insurance", expiry_date=expiry
            )
            queued, msgids = _run_watcher(
                vehicle.vehicle_compliance_expiry_watch, [row]
            )
            self._assert_operator_sentence(queued)
            seen[label] = [m for m in msgids if "{0}" in m]

        for fragment in FRAGMENTS:
            for label, msgids in seen.items():
                self.assertNotIn(
                    fragment,
                    msgids,
                    f"{label}: {fragment!r} was handed to the translator on its own",
                )

        self.assertNotEqual(
            seen["expired"],
            seen["expiring"],
            "expired and expiring must be two separate translatable sentences",
        )


if __name__ == "__main__":
    unittest.main()
