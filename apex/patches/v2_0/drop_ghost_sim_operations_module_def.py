# Copyright (c) 2026, AFMCO and contributors
"""Delete the ghost ``SIM Operations`` Module Def that a fresh install minted (A-187).

``fold_sim_operations_into_logistay`` already drops this row — but only on a site that
actually RUNS it. Two framework facts left a hole it can never reach:

  * ``modules.txt`` still declared ``SIM Operations`` after the fold, and
    ``frappe.installer.add_module_defs`` (installer.py:686-692) inserts one Module Def
    per line of ``frappe.get_module_list(app)`` on every ``install-app``;
  * ``install_app`` then calls ``set_all_patches_as_completed`` (installer.py:324-325),
    which logs the fold patch as done WITHOUT running it.

So every site installed between the fold and this change carries a Module Def for a
module that owns no DocType, Report, Workspace, Notification or Number Card, and no
code — a ghost in the Desk module list, the User "Block Modules" picker and every
module-count claim. ``modules.txt`` no longer declares it, so no NEW site can mint one;
this patch is the only thing that reaches the sites that already did.

post_model_sync: it reads no column model sync drops, so pre_model_sync buys nothing,
and it must land AFTER ``sync_all`` has re-imported every shipped JSON under its real
module — otherwise the reference check below could see a stamp sync is about to rewrite
anyway. Registered last in the section so the fold patch's dotted-path sweep and
workspace cleanup finish first on a site where both are pending.

Idempotent by construction: both steps below are existence-gated, so a second migrate
matches nothing, and a site that never had the module is a complete no-op.
"""

from __future__ import annotations

import frappe

# Reuse the fold's proven, already-tested steps rather than copy them: the two patches
# must agree on what "nothing references it" means, and a fork would drift.
from apex.patches.v2_0 import fold_sim_operations_into_logistay as fold


def execute() -> None:
    # Repoint first: deleting a Module Def a live record still names would leave a
    # dangling Link. On the sites this patch exists for there is nothing to repoint.
    fold._repoint_module_stamps()
    # db.delete, never delete_doc: Module Def.on_trash rewrites the app's modules.txt on
    # disk and deletes the module folder when developer_mode is on.
    fold._drop_retired_module_def()
    frappe.db.commit()
