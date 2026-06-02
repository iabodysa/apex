"""Superseded — retired in the seed consolidation (M-10/M-11).

Operational Kanban Boards are now provisioned by the data-driven loader
``apex_habitat.tools.setup.seed.seed_all`` (create-only JSON under
``tools/setup/data/habitat/kanban_board.json``), wired into after_install /
after_migrate. This patch already ran on every existing site; it is kept in
``patches.txt`` as a no-op so its Patch Log entry stays valid and lagging sites
do not error on a removed import.
"""


def execute():
    pass
