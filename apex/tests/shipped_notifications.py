# Copyright (c) 2026, AFMCO and contributors
"""Read the app's shipped is_standard Notification JSON straight off disk.

The sibling of ``shipped_doctypes.py``, and it exists for the same reason: a
second guard needed the same parse and the copy-paste detector would have caught
the duplicate. ``test_release_hygiene`` already carried two private scanners over
this directory tree (one harvesting recipient roles, one listing companion dirs);
both now read from here, so the three consumers cannot drift apart on what
"a shipped notification" means.

Deliberately NOT named ``test_*``: ``tests/test_no_cross_test_imports.py`` bans a
test module importing a sibling test module, and ``apex_core/utils/
test_notification_role_guard.py`` is colocated with the guard it proves. A plain
name is the sanctioned shape for shared test logic (the same reason
``factories.py``, ``shipped_doctypes.py`` and ``workspace_reachability.py``
carry plain names), and it keeps the colocation ratchet — which counts
``test_*.py`` under ``tests/`` — unmoved.
"""

import os
from pathlib import Path

import apex

APP_ROOT = str(Path(apex.__file__).resolve().parent)

NOTIFICATION_GLOB = os.path.join(APP_ROOT, "*", "notification", "*", "*.json")

