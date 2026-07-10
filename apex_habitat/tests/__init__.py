"""Test package for apex_habitat.

Test-placement rule (where each test lives):
  * A test of ONE DocType controller -> co-locate as
    ``<module>/doctype/<dt>/test_<dt>.py`` (Frappe native convention).
  * A test of ONE api/page backend module -> co-locate as
    ``<module>/api/test_<name>.py``.
  * A narrow unit test of a utils-package member MAY co-locate inside that
    package (precedent: ``apex_core/utils/test_portal_bootstrap.py``).
  * A module-root unit test is allowed ONLY when a same-named module-root
    source file is its direct target (precedent:
    ``apex_core/test_payment_router.py`` <-> ``apex_core/payment_router.py``).
  * Everything else -- cross-module, integration, workflow, security,
    seed-parity, scheduler, coverage -- lives HERE in ``apex_habitat/tests/``.

Shared fixtures go in ``tests/factories.py`` (never imported from a sibling
``test_*`` module -- enforced by ``test_no_cross_test_imports.py``).
"""

