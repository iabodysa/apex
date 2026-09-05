# Copyright (c) 2026, Apex contributors

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
    return bootstrap_portal_context(context, "/safety")
