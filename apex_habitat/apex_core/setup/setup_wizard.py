"""Apex first-install Setup Wizard integration (native Frappe setup wizard).

On a fresh site, Frappe's setup wizard renders an extra "Apex Configuration" slide
(registered by public/js/apex_setup_wizard.js via the `setup_wizard_requires` hook).
The operator's choices flow into the wizard args and land here at completion
(`setup_wizard_complete` hook), where they are applied — ONCE. The app-wide finance
defaults land on the Apex Settings single (shared by Habitat and Salis); the
housing-scoped deduction toggles land on Habitat Settings.

Safe-by-default: a toggle the operator did not tick stays OFF, so the app never
deducts a housing allowance or posts to the GL unless the operator explicitly opts
in during setup. Idempotent: re-running with the same args is harmless.
"""

import frappe
from frappe import _
from frappe.utils import cint


def get_setup_stages(args=None):
    """`setup_wizard_stages` hook — a tracked stage that applies the Apex choices
    during the native wizard's completion sequence."""
    return [
        {
            "status": _("Configuring Apex"),
            "fail_msg": _("Failed to apply the Apex configuration"),
            "tasks": [
                {
                    "fn": apply_apex_setup,
                    "args": args,
                    "fail_msg": _("Failed to apply the Apex configuration"),
                    "app_name": "apex_habitat",
                }
            ],
        }
    ]


def setup_wizard_complete(args=None):
    """`setup_wizard_complete` hook — apply the operator's first-run choices."""
    apply_apex_setup(args)


def apply_apex_setup(args=None):
    """Write the operator's Setup-Wizard choices (create-only semantics on the
    toggles: default OFF unless explicitly chosen). No commit — Frappe commits
    after all setup stages succeed.

    The app-wide finance defaults (``default_payment_method``, ``enable_gl_posting``)
    live on the Apex Settings single because they serve both Habitat and Salis; the
    housing-scoped deduction toggles stay on Habitat Settings."""
    args = frappe._dict(args or {})

    payment_method = args.get("apex_default_payment_method")

    # [#knd5u7]
    apex = frappe.get_single("Apex Settings")
    if payment_method:
        apex.default_payment_method = payment_method
    # [#cyuc3q]
    apex.enable_gl_posting = 1 if cint(args.get("apex_post_gl")) else 0
    apex.save(ignore_permissions=True)

    # [#4e5jex]
    settings = frappe.get_single("Habitat Settings")
    # [#d1oej5]
    settings.enable_housing_allowance_deduction = 1 if cint(args.get("apex_deduct_housing_allowance")) else 0
    settings.enable_damage_deduction = 1 if cint(args.get("apex_deduct_damage")) else 0
    try:
        settings.save(ignore_permissions=True)
    except frappe.ValidationError:
        # [#3jakkl]
        # [#g1g2gb]
        # [#p8nhid]
        # [#qwowt8]
        frappe.clear_last_message()
        settings.reload()
        settings.enable_housing_allowance_deduction = 0
        settings.enable_damage_deduction = 0
        settings.save(ignore_permissions=True)
        frappe.msgprint(
            _(
                "Payment method saved. To enable salary deductions, set the "
                "authorizer and salary components in Habitat Settings first, then "
                "turn them on there."
            ),
            title=_("Apex Setup"),
            indicator="orange",
        )
