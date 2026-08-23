# Copyright (c) 2026, afmcoltd
"""Install-time and migrate-time setup for the app.

Everything here runs from the ``after_install`` / ``after_migrate`` hooks, under Administrator,
against a site that has no operator on it yet. That is why the writes pass ``ignore_permissions``:
there is no session user whose roles could be consulted, and a DocPerm added to make these saves
legal would then also be live for every real operator afterwards. This is the installer context —
it is the rare case the rule allows, not a shortcut around a missing role.
"""
import json

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSetMultipleRootsError, rebuild_tree

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import seed_auto_email_reports
from apex.apex_core.setup.seeders.maintenance_material_template_seed import (
    seed_templates,
)
from apex.apex_core.setup.seeders.portal_identity_seed import seed_portal_identities


ACCOMMODATION_ITEM_GROUPS = [
    "Accommodation Bedding",
    "Accommodation Furniture",
    "Accommodation Appliances",
    "Accommodation Kitchenware",
    "Accommodation Sanitary and Cleaning",
]

KEPT_GENDERS = ("Male", "Female")

def after_install():
    """Runs the after-install seed: roles, profiles, item defaults and material templates.

    The Custody Asset Category, Custody Article and Operational Depreciation Policy
    masters ship as fixtures (``apex/fixtures/``). Nothing here may read one:
    ``frappe.installer.install_app`` runs this function at :327 and ``sync_fixtures``
    only at :334, so on a fresh install every fixture row is still absent while this
    runs. Work that needs a fixture belongs in ``after_sync``, which the same function
    calls at :338.
    """
    create_roles()
    frappe.db.commit()
    create_role_profiles()
    create_accommodation_item_defaults(allow_deferred=True)
    seed_templates()
    seed_auto_email_reports()
    seed_portal_identities()
    restrict_genders()
    frappe.clear_cache()


def after_migrate():
    """Bring an UPGRADED site to the same shipped state a fresh install reaches.

    ``create_accommodation_item_defaults`` keeps ``allow_deferred`` because it needs
    ERPNext's Item Group root, which an incomplete site may not have yet — deferring is
    correct there and a hard failure is not.
    """
    seed_portal_identities()
    seed_templates()
    return create_accommodation_item_defaults(allow_deferred=True)


def create_accommodation_item_defaults(*, allow_deferred=False):
    """Seed accommodation Item Groups and Items once ERPNext has its root.

    Raises ``frappe.DoesNotExistError`` (frappe/exceptions.py) when the root is absent
    and ``allow_deferred`` is false. The flag exists because the SAME function runs at
    two moments: from ``after_install``, where erpnext's own setup has not created the
    Item Group root yet and deferring is correct, and from the setup wizard's
    completion, where the root must exist and a silent skip would leave a site with no
    accommodation items and no error.
    """
    item_group_root = _get_item_group_root()
    if not item_group_root:
        if allow_deferred:
            return False
        raise frappe.DoesNotExistError(
            _("ERPNext Item Group root is required before seeding accommodation items.")
        )

    create_accommodation_item_groups(item_group_root)
    create_accommodation_items()
    return True


def _get_item_group_root():
    """Returns the single root Item Group, or None when ERPNext has not created one yet."""
    roots = frappe.get_all(
        "Item Group",
        filters={"parent_item_group": ["is", "not set"]},
        pluck="name",
    )
    if len(roots) > 1:
        raise NestedSetMultipleRootsError(_("Multiple root nodes not allowed."))
    return roots[0] if roots else None


def create_accommodation_item_groups(item_group_root):
    """Create accommodation groups under the installed ERPNext root."""

    root_lft, root_rgt = frappe.db.get_value(
        "Item Group",
        item_group_root,
        ["lft", "rgt"],
    )
    if root_lft is None or root_rgt is None or root_lft >= root_rgt:
        rebuild_tree("Item Group", "parent_item_group")

    for group in ACCOMMODATION_ITEM_GROUPS:
        exists = frappe.db.exists("Item Group", group)
        existing_parent = frappe.db.get_value("Item Group", group, "parent_item_group")
        parent_is_group = (
            frappe.db.get_value("Item Group", existing_parent, "is_group")
            if existing_parent
            else False
        )
        if exists and parent_is_group:
            continue
        if exists:
            doc = frappe.get_doc("Item Group", group)
            doc.parent_item_group = item_group_root
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(
                {
                    "doctype": "Item Group",
                    "item_group_name": group,
                    "parent_item_group": item_group_root,
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)


def restrict_genders():
    """Leave only Male and Female on the site, keeping any Gender a record still points at.

    ``frappe.desk.page.setup_wizard.install_fixtures.update_genders`` creates seven Genders at
    setup time. Apex offers two, so the surplus is removed once — at install for a new site and
    by a patch for a site that already ran the wizard. It is deliberately absent from
    ``after_migrate``: a Gender an operator adds later is theirs, and a migrate that deleted it
    every run would be the app arguing with its own operator.

    Deletion goes through ``frappe.delete_doc``, so the framework's own link check decides what
    may go. A Gender still referenced by an Employee survives and is reported, rather than
    being forced out from under the row that uses it.
    """
    surplus = [
        name for name in frappe.get_all("Gender", pluck="name") if name not in KEPT_GENDERS
    ]
    removed, kept = [], []
    for name in surplus:
        try:
            frappe.delete_doc("Gender", name, ignore_permissions=True)
            removed.append(name)
        except frappe.LinkExistsError:
            kept.append(name)
    if kept:
        print(f"apex: Gender still in use, left in place: {kept}")
    return {"removed": removed, "in_use": kept}


def create_accommodation_items():
    """Insert the accommodation Items after their Item Groups are available."""
    for record in _load_accommodation_item_records():
        if frappe.db.exists("Item", record["item_code"]):
            continue
        frappe.get_doc(record).insert(ignore_permissions=True)


def _load_accommodation_item_records():
    """Loads the bundled accommodation Item records from their JSON fixture file.

    ``frappe.get_app_path`` (frappe/__init__.py:1484) resolves the installed app's own
    directory, so the records read are the ones that SHIPPED with the running version
    rather than whatever path the bench process started from.
    """
    data_path = frappe.get_app_path(
        "apex",
        "apex_core",
        "setup",
        "accommodation_items.json",
    )
    with open(data_path, encoding="utf-8") as source:
        return json.load(source)


def create_roles():
    """Creates the one standing Apex role no shipped DocType names in a permissions block.

    ``DocType.make_module_and_roles`` (frappe/core/doctype/doctype/doctype.py:1852-1889)
    creates a Role for every role a shipped DocType's ``permissions`` table names, the
    moment that DocType syncs, so a role that appears in any permissions block needs no
    line here. Admin Manager appears in none, which is why nothing else on the site
    would ever create it. Give it a DocPerm row anywhere and this function is dead.
    """
    if not frappe.db.exists("Role", "Admin Manager"):
        doc = frappe.new_doc("Role")
        doc.role_name = "Admin Manager"
        doc.desk_access = 0
        doc.insert(ignore_permissions=True)


def create_role_profiles():
    """Creates the standing Habitat and Salis Role Profiles that bundle roles for onboarding."""
    profiles = {
        "Habitat Accommodation Manager": ["Accommodation Manager"],
        "Habitat Resident Supervisor": ["Resident Supervisor"],
        "Habitat Finance Reviewer": ["Finance Manager", "Internal Auditor"],
        "Habitat Maintenance Technician": ["Maintenance Technician"],
        "Habitat Cleaning Supervisor": ["Cleaning Supervisor"],
        "Habitat Safety Officer": ["Safety Officer"],
        "Habitat Resident Request Coordinator": ["Resident Request Coordinator"],
    }
    for profile_name, roles in profiles.items():
        if not frappe.db.exists("Role Profile", profile_name):
            doc = frappe.new_doc("Role Profile")
            doc.role_profile = profile_name
            for role in roles:
                doc.append("roles", {"role": role})
            doc.insert(ignore_permissions=True)
            doc.unlock()
    if not frappe.db.exists("Role Profile", "Salis Driver"):
        doc = frappe.new_doc("Role Profile")
        doc.role_profile = "Salis Driver"
        doc.append("roles", {"role": "Driver"})
        doc.insert(ignore_permissions=True)
        doc.unlock()

