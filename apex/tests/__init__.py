# Copyright (c) 2026, afmcoltd

"""Test package for apex.

A test lives in the folder of the file it tests, which is the framework's own
layout: ``<module>/doctype/<dt>/test_<dt>.py`` beside ``<dt>.py`` and ``<dt>.json``,
``<module>/report/<report>/test_<report>.py`` beside the report script, and the
same for an api, utils, tasks, patch or www module. Frappe discovers a test by its
location and its ``test_`` prefix (``frappe/test_runner.py:149`` walks the whole app
path), so colocation costs no discovery.

Nothing else belongs here. This directory holds shared fixtures and the readers the
colocated tests import — ``factories.py`` above all — and no test of its own. A test
that grades the SHAPE of the source rather than the behaviour of the app is the
repository owner's tooling, not the product's, and lives outside the app.

DECISION (2026-08-16): a test fixture's ``ignore_permissions`` is exempt from the
per-site written-reason requirement that ``ctl bypass check`` grades. A fixture
inserts a synthetic record as a test-only user who holds no real DocPerm grant by
design — the record exists to exercise the code under test, not to model what a
real operator can write — so the "what breaks without it" framing that a
production bypass must answer does not transfer: without it, every fixture would
need its own role and permission scaffolding just to exist, which tests the
permission system a second time instead of the behaviour the test is for. The
close condition this project holds itself to (SILENT == 0, not raw-count == 0)
therefore reads against ``ctl bypass check --skip-tests``, which grades only
``apex/`` source outside ``tests/`` and outside any ``test_*.py`` file and says so
in its own verdict line. A bypass inside a shipped, non-test module still needs
its reason named in the enclosing docstring exactly as before.
"""
