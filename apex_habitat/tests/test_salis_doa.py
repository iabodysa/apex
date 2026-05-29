"""Tests for the Delegation-of-Authority engine (salis_lib) and the Approval
Request segregation-of-duties control."""

import unittest

import frappe

from apex_habitat.salis import salis_lib


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


class TestTierLadder(unittest.TestCase):
    def test_tier_rank(self):
        self.assertEqual(salis_lib.tier_rank("Supervisor"), 0)
        self.assertEqual(salis_lib.tier_rank("Operations"), 3)
        self.assertEqual(salis_lib.tier_rank("Nonsense"), -1)
        self.assertEqual(salis_lib.tier_rank(None), -1)

    def test_next_tier(self):
        self.assertEqual(salis_lib.next_tier("Supervisor"), "Project")
        self.assertEqual(salis_lib.next_tier("Regional"), "Operations")
        self.assertIsNone(salis_lib.next_tier("Operations"))
        self.assertIsNone(salis_lib.next_tier("Nonsense"))


class TestUserTier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.sup = _user("doa_sup@example.com", "Fleet Supervisor")
        cls.ops = _user("doa_ops@example.com", "Fleet Manager")
        frappe.db.commit()

    def test_user_max_tier(self):
        self.assertEqual(salis_lib.user_max_tier(self.sup), "Supervisor")
        self.assertEqual(salis_lib.user_max_tier(self.ops), "Operations")

    def test_escalation_target(self):
        # A Supervisor approving an Operations-tier request must escalate.
        self.assertEqual(salis_lib.escalation_target("Operations", self.sup), "Operations")
        # An Operations-tier approver is within authority.
        self.assertIsNone(salis_lib.escalation_target("Operations", self.ops))
        self.assertIsNone(salis_lib.escalation_target(None, self.sup))


class TestApprovalRequestSoD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.a = _user("doa_a@example.com", "Fleet Manager")
        frappe.db.commit()

    def test_approver_equals_requester_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "Approval Request", "request_type": "Other",
                "requested_by": self.a, "approver": self.a, "decision": "Approved",
            }).insert(ignore_permissions=True)


class TestEnsureApproval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.sup = _user("doa_sup2@example.com", "Fleet Supervisor")
        cls.ops = _user("doa_ops2@example.com", "Fleet Manager")
        cls.req = _user("doa_req2@example.com", "Fleet Project Manager")
        frappe.db.commit()

    def _ref_vehicle(self, plate):
        v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not v:
            v = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": plate,
                                "status": "Active"}).insert(ignore_permissions=True).name
        return v

    def _approved(self, plate, approver):
        ref = self._ref_vehicle(plate)
        doc = frappe.get_doc({
            "doctype": "Approval Request", "request_type": "Other",
            "requested_by": self.req, "approver": approver,
            "reference_doctype": "Salis Vehicle", "reference_name": ref,
            "decision": "Approved",
        }).insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return ref

    def test_missing_approval_blocks(self):
        with self.assertRaises(frappe.ValidationError) as cm:
            salis_lib.ensure_approval("Salis Vehicle", "NO SUCH VEHICLE")
        self.assertIn("Approval Request", str(cm.exception))

    def test_under_tier_approver_blocks(self):
        ref = self._approved("DOA UT 1", approver=self.sup)
        with self.assertRaises(frappe.ValidationError) as cm:
            salis_lib.ensure_approval("Salis Vehicle", ref, required_tier="Operations")
        self.assertIn("tier", str(cm.exception).lower())

    def test_sufficient_tier_passes(self):
        ref = self._approved("DOA OK 1", approver=self.ops)
        self.assertTrue(
            salis_lib.ensure_approval("Salis Vehicle", ref, required_tier="Operations")
        )
