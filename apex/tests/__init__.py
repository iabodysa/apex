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
"""
