# Copyright (c) 2026, afmcoltd
"""Retire the onboarding step left pointing at a folded Settings Single.

``Review Apex Integration Settings`` was written when the integration fields lived in
a Single of their own. That Single was folded into Salis Settings, and the step was
re-pointed at the new home — which left the setup wizard with TWO steps that open the
same record, ``Review Salis Settings`` and ``Confirm Salis Settings``, each with its
own label and its own completion tick. The subject the retired step carried, the
frontend URL and the approved origins, is now named by the surviving step's
description.

Deleting the shipped file is not enough on an upgraded site. ``import_file`` only ever
inserts or updates the records a module ships; nothing walks the module's folder to
find records that are no longer there, so a removed Onboarding Step keeps its row and
keeps rendering in the wizard. Removing the row is what this patch is for.

The Onboarding Step Map row inside Apex Setup is carried by that module onboarding's
own JSON, which migrate re-imports whole, so the child row disappears with the file
and needs no separate delete here.
"""

import frappe


STEP = "Review Apex Integration Settings"


def execute():
    """Delete the retired Onboarding Step record if this site still carries it."""
    if frappe.db.exists("Onboarding Step", STEP):
        frappe.delete_doc("Onboarding Step", STEP, ignore_missing=True)
