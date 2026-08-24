# Copyright (c) 2026, AFMCO and contributors

from unittest.mock import patch

import frappe


class as_user:

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self._prev = frappe.session.user
        frappe.set_user(self.user)
        return self

    def __exit__(self, *exc):
        frappe.set_user(self._prev)
        return False






class lending_installed:

    def __enter__(self):
        installed = frappe.get_installed_apps()
        apps = list(installed) + ["lending"] if "lending" not in installed else list(installed)
        self._patch = patch("frappe.get_installed_apps", return_value=apps)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False


def approve_rental_settlement(rs, manager):
    from frappe.model.workflow import apply_workflow, get_workflow_name

    if get_workflow_name("Rental Settlement") == "Rental Settlement Workflow":
        frappe.set_user(manager)
        apply_workflow(rs, "Reconcile")
        rs.reload()
        apply_workflow(rs, "Approve")
        frappe.set_user("Administrator")
    else:
        rs.status = "Approved"
        rs.save(ignore_permissions=True)
        rs.submit()
    rs.reload()
    return rs




def submit_via_workflow(doc):
    from frappe.model.workflow import get_workflow, get_workflow_name
    from frappe.utils import cint

    if get_workflow_name(doc.doctype):
        workflow = get_workflow(doc.doctype)
        submit_state = next(
            (s.state for s in workflow.states if cint(s.doc_status) == 1), None
        )
        if submit_state:
            frappe.db.set_value(
                doc.doctype,
                doc.name,
                workflow.workflow_state_field,
                submit_state,
                update_modified=False,
            )
            doc.reload()
    doc.submit()


def _user(email, role):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email,
                            "first_name": email.split("@")[0], "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
    else:
        u = frappe.get_doc("User", email)
    if role not in frappe.get_roles(email):
        u.add_roles(role)
    return email


def _project(project_name="QA Scope Project"):
    from apex.tests.factories import make_project

    return make_project(project_name)


def _grant_project(user, project):
    if not frappe.db.exists(
        "User Permission", {"user": user, "allow": "Project", "for_value": project}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": user,
                "allow": "Project",
                "for_value": project,
            }
        ).insert(ignore_permissions=True)
