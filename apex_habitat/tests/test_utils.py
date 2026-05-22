"""
Test utilities and fixtures for apex_habitat.

Test execution requires a configured Frappe test environment, which is not
created or modified by this repository.
"""

from __future__ import annotations

try:
    import frappe
    from frappe.tests.utils import FrappeTestCase
    UnitTestCase = FrappeTestCase
except Exception:  # pragma: no cover
    # Keep imports optional for environments where Frappe isn't installed.
    frappe = None
    FrappeTestCase = object  # type: ignore
    UnitTestCase = object  # type: ignore


class ApexHabitatTestCase(FrappeTestCase):
    """Base test case for apex_habitat integration tests."""


class ApexHabitatUnitTestCase(UnitTestCase):
    """Base test case for apex_habitat unit tests (no database)."""

