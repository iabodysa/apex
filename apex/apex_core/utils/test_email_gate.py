# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.email_gate.email_enabled.

The gate reads one Single flag and coerces it via ``cint`` + ``bool``. The DB
read is mocked so the coercion (including the fresh-site ``None`` default) is
exercised without a live site.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.apex_core.utils import email_gate


class TestEmailEnabled(unittest.TestCase):
    def _run(self, single_value):
        with mock.patch.object(email_gate, "frappe") as mf:
            mf.db.get_single_value.return_value = single_value
            return email_gate.email_enabled()

    def test_truthy_flag_enables(self):
        self.assertIs(self._run(1), True)
        self.assertIs(self._run("1"), True)

    def test_falsy_flag_disables(self):
        self.assertIs(self._run(0), False)

    def test_missing_single_defaults_disabled(self):
        # Fresh site: the Single row does not exist yet -> get_single_value None.
        self.assertIs(self._run(None), False)


if __name__ == "__main__":
    unittest.main()
