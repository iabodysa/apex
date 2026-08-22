# Copyright (c) 2026, Apex contributors
"""The merged Habitat portal's second door, served at /safety.

/safety and /housing are one application. This module exists so the safety bookmark,
the /apps tile and every link that already points here keep landing on the same
screen they always did — the portal opens on the safety round instead of the count.

The gate, the section map and the realtime configuration all come from www/housing.py
so there is one copy of them; SAFETY_ROLES is re-exported here because that is where
readers of this route look for it.
"""

from apex.www.housing import (
    PORTAL_ROLES,
    SAFETY_ROLES,
    bootstrap_portal_context,
    has_apps_screen_access,
)

__all__ = [
    "PORTAL_ROLES",
    "SAFETY_ROLES",
    "has_apps_screen_access",
]

def get_context(context):
    """Bootstraps the merged portal at its safety door."""
    return bootstrap_portal_context(context, "/safety", "safety")
