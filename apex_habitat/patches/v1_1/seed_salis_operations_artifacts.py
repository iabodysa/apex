"""Superseded — retired in the seed consolidation (M-10/M-11).

The Salis Kanban Boards and Assignment Rules are now provisioned by the
data-driven loader ``apex_habitat.apex_core.setup.seed.seed_all`` (create-only JSON
under ``apex_core/setup/data/salis/``), wired into after_install / after_migrate.
This patch already ran on every existing site; it is kept in ``patches.txt`` as
a no-op so its Patch Log entry stays valid and lagging sites do not error on a
removed import.
"""


def execute():
    pass
