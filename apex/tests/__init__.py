"""Test package for apex.

Test-placement rule (where each test lives):
  * A test of ONE DocType controller -> co-locate as
    ``<module>/doctype/<dt>/test_<dt>.py`` (Frappe native convention).
  * A test of ONE api/page backend module -> co-locate as
    ``<module>/api/test_<name>.py``.
  * A test of ONE utils / tasks / seeder / patch / www module -> co-locate
    inside that package (e.g. ``apex_core/utils/test_portal_bootstrap.py``,
    ``habitat/tasks/test_custody_digest.py``, ``patches/v2_0/test_sim_migration.py``,
    ``www/test_portal_xss.py``).
  * A module-root unit test is allowed when a module-root source file is its
    direct target (e.g. ``apex_core/test_payment_router.py`` <->
    ``apex_core/payment_router.py``, ``salis/test_salis_engines.py``).
  * Only what has NO single home stays HERE in ``apex/tests/``: the app-wide
    release-hygiene and schema guards, and the handful of suites whose invariant
    genuinely spans two or more unrelated units.

``test_colocation_ratchet.py`` enforces this — the central directory may only
shrink, and a new central ``test_*.py`` fails the build. Frappe discovers tests
wherever they sit (``frappe/test_runner.py:149`` os.walks the whole app path),
so colocation costs no discovery.

A NEW app-wide guard does NOT come here (owner decision, 2026-07-28). It colocates
beside the module that owns the invariant's DESTINATION -- the place a violation
would be written, not the many places it could be written from. A sweep over the
whole tree is still colocated by that rule: the guard on ledger concealment lives
with the ledger, not in a central "guards" bucket. This keeps the ratchet strictly
shrinking and needs no admission path into ``_CENTRAL_BY_NECESSITY``, which stays
frozen. If no single destination module owns the invariant, that is the signal the
invariant is really two, not that the guard belongs here.

Shared fixtures go in ``tests/factories.py`` (never imported from a sibling
``test_*`` module -- enforced by ``test_no_cross_test_imports.py``).
"""

