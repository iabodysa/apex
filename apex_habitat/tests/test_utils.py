# Copyright (c) 2026, AFMCO and contributors
"""
Test utilities and fixtures for apex_habitat.

The base test cases now live in ``tests/factories.py`` (P-135) — the single
non-``test_*`` home the cross-test-import ratchet points every consumer at. This
module re-exports them so DocType-level ``test_*`` files (outside ``tests/``, and
outside the ratchet's scope) keep their historical import path.
"""

from __future__ import annotations

from apex_habitat.tests.factories import (  # noqa: F401  (re-export)
    ApexHabitatTestCase,
    ApexHabitatUnitTestCase,
)

