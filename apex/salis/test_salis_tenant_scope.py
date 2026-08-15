# Copyright (c) 2026, AFMCO and contributors
"""Project row-scoping for the Salis indirect-tenant DocTypes.

These DocTypes carry no own ``project`` field; they reach their tenant through a
Salis Driver link (``driver`` / ``related_driver`` -> Salis Driver -> project) or,
for Movement Cost Transfer, through two direct project Links (``from_project`` /
``to_project``). Before this pass a Fleet Supervisor scoped to one project could
enumerate every project's driver attendance, stops, boarding scans, incidents,
write-offs, clearances, vehicle stops and cost transfers in the list/report view
and open them directly — a cross-project PII / disciplinary leak.

BOTH SIDES COME OUT OF ONE TABLE. ``project_scope_query`` renders the list
fragment for the DocType it is given and ``project_scoped_has_permission`` routes
the document check on ``doc.doctype``; each reads that DocType's row in
``SALIS_SCOPE``, so the fragment and the check cannot disagree. Eight of the nine
DocTypes here take the ``driver_chain`` rule; Movement Cost Transfer takes the
``dual`` rule (``movement_cost_transfer_has_permission``).

Each test proves: a Fleet Supervisor scoped to Project A sees zero rows resolving
to Project B (the generated query fragment, run as a real subquery, excludes B's
driver, and the has_permission hook denies a B-resolved doc); oversight roles are
unaffected (empty fragment / deferred hook); and the Driver if_owner self-record
path still returns the driver's own rows where such a DocPerm exists.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.permissions import project_scope_query, project_scoped_has_permission
from apex.tests._helpers import _user
from apex.tests.factories import make_project

# Each driver-chain DocType, the field naming its Salis Driver, and whether
# ``SALIS_SCOPE`` gives it an ``own="owner"`` basis. That third column is the whole
# difference between the two groups: with it the fragment ORs in ``owner`` = me and
# the document rule defers on the acting user's own STORED row; without it neither
# does, and only the driver chain decides.
DRIVER_CHAIN_CASES = (
    ("Driver Attendance", "driver", True),
    ("Driver Suspension", "driver", True),
    ("Boarding Scan Log", "driver", True),
    ("Vehicle Damage Write-Off", "driver", False),
    ("Vehicle Incident", "driver", True),
    ("Driver Clearance", "driver", False),
    ("Vehicle Suspension", "related_driver", False),
)

SCOPED_DOCTYPES = tuple(doctype for doctype, _field, _own in DRIVER_CHAIN_CASES) + (
    "Movement Cost Transfer",
)


class TestSalisTenantScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = make_project("Tenant Scope A")
        cls.pb = make_project("Tenant Scope B")
        cls.sup = _user("tenant_sup@example.com", "Fleet Supervisor")
        cls.mgr = _user("tenant_mgr@example.com", "Fleet Manager")
        cls.drv = _user("tenant_drv@example.com", "Driver")
        cls._user_perm(cls.sup, cls.pa)
        cls.drv_a = cls._driver("Tenant Driver A", cls.pa)
        cls.drv_b = cls._driver("Tenant Driver B", cls.pb)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        for d in (cls.drv_a, cls.drv_b):
            if frappe.db.exists("Salis Driver", d):
                frappe.delete_doc("Salis Driver", d, ignore_permissions=True, force=True)
        for p in (cls.pa, cls.pb):
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()


    @staticmethod
    def _user_perm(user, project):
        if not frappe.db.exists(
            "User Permission",
            {"allow": "Project", "for_value": project, "user": user},
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "allow": "Project",
                    "for_value": project,
                    "user": user,
                }
            ).insert(ignore_permissions=True)

    @staticmethod
    def _driver(full_name, project):
        name = frappe.db.get_value(
            "Salis Driver", {"full_name": full_name}, "name"
        )
        if name:
            return name
        doc = frappe.new_doc("Salis Driver")
        doc.full_name = full_name
        doc.project = project
        doc.flags.ignore_validate = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        return doc.name


    def _resolves_to_b(self, fragment, column):
        """True if a row pointing at the Project-B driver passes ``fragment``.

        Runs the generated WHERE fragment as a real query against a one-row table
        carrying the B driver in ``column``; an empty result proves the supervisor
        sees zero rows resolving to Project B.
        """
        col = column.strip("`")
        rows = frappe.db.sql(
            "select 1 from (select %s as `{c}`, %s as `owner`) t where {frag}".format(
                c=col, frag=fragment
            ),
            (self.drv_b, "stranger@example.com"),
        )
        return bool(rows)

    def _resolves_to_a(self, fragment, column):
        col = column.strip("`")
        rows = frappe.db.sql(
            "select 1 from (select %s as `{c}`, %s as `owner`) t where {frag}".format(
                c=col, frag=fragment
            ),
            (self.drv_a, "stranger@example.com"),
        )
        return bool(rows)


    def test_driver_attendance_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Driver Attendance")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertIn("owner", frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_driver_stop_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Driver Suspension")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_boarding_scan_log_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Boarding Scan Log")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_vehicle_damage_write_off_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Vehicle Damage Write-Off")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertNotIn("owner", frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_vehicle_incident_query_excludes_other_project(self):
        """Vehicle Incident carries ``own="owner"``, so the fragment ORs it in."""
        frag = project_scope_query(self.sup, doctype="Vehicle Incident")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertIn("owner", frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_driver_clearance_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Driver Clearance")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_vehicle_stop_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Vehicle Suspension")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertIn("related_driver", frag)
        self.assertFalse(self._resolves_to_b(frag, "`related_driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`related_driver`"))

    def test_movement_cost_transfer_query_excludes_other_project(self):
        frag = project_scope_query(self.sup, doctype="Movement Cost Transfer")
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        rows = frappe.db.sql(
            "select 1 from (select %s as `from_project`, %s as `to_project`) t "
            "where {frag}".format(frag=frag),
            (self.pb, self.pb),
        )
        self.assertFalse(bool(rows))
        rows_a = frappe.db.sql(
            "select 1 from (select %s as `from_project`, %s as `to_project`) t "
            "where {frag}".format(frag=frag),
            (self.pb, self.pa),
        )
        self.assertTrue(bool(rows_a))


    def test_oversight_sees_all(self):
        for doctype in SCOPED_DOCTYPES:
            self.assertEqual(
                project_scope_query(self.mgr, doctype=doctype),
                "",
                "%s must not restrict oversight" % doctype,
            )


    def test_driver_self_record_path_preserved(self):
        for doctype, field, own in DRIVER_CHAIN_CASES:
            if not own:
                continue
            frag = project_scope_query(self.drv, doctype=doctype)
            self.assertIn("owner", frag)
            self.assertNotIn(self.pa, frag)
            self.assertNotIn(self.pb, frag)
            rows = frappe.db.sql(
                "select 1 from (select %s as `{c}`, %s as `owner`) t "
                "where {frag}".format(c=field, frag=frag),
                (self.drv_b, self.drv),
            )
            self.assertTrue(bool(rows), "%s must keep the driver's own row" % doctype)


    def test_driver_chain_has_permission_blocks_other_project(self):
        for doctype, field, _own in DRIVER_CHAIN_CASES:
            doc_b = frappe._dict(
                {"doctype": doctype, field: self.drv_b, "owner": "stranger@example.com"}
            )
            self.assertFalse(
                project_scoped_has_permission(doc_b, "read", user=self.sup),
                "%s must deny a Project-B doc to the scoped supervisor" % doctype,
            )
            doc_a = frappe._dict(
                {"doctype": doctype, field: self.drv_a, "owner": "stranger@example.com"}
            )
            self.assertIsNone(
                project_scoped_has_permission(doc_a, "read", user=self.sup),
                "%s must allow a Project-A doc to the scoped supervisor" % doctype,
            )
            self.assertIsNone(project_scoped_has_permission(doc_b, "read", user=self.mgr))

    def test_if_owner_has_permission_keeps_own_row(self):
        """The own-row basis is exactly the DocTypes ``SALIS_SCOPE`` marks with it.

        Asserted as a pair: a stored out-of-project row owned by the acting user
        defers where the DocType carries ``own="owner"``, and is still denied where
        it does not — so a rule that granted ownership everywhere fails the second
        half, and one that granted it nowhere fails the first.
        """
        for doctype, field, own in DRIVER_CHAIN_CASES:
            mine = frappe._dict(
                {"doctype": doctype, field: self.drv_b, "owner": self.drv}
            )
            verdict = project_scoped_has_permission(mine, "read", user=self.drv)
            if own:
                self.assertIsNone(verdict, "%s must keep the Driver's own row" % doctype)
            else:
                self.assertFalse(
                    verdict, "%s has no own-row basis and must stay project-bound" % doctype
                )

    def test_movement_cost_transfer_has_permission(self):
        a_in = frappe._dict(
            {
                "doctype": "Movement Cost Transfer",
                "from_project": self.pb,
                "to_project": self.pa,
            }
        )
        b_only = frappe._dict(
            {
                "doctype": "Movement Cost Transfer",
                "from_project": self.pb,
                "to_project": self.pb,
            }
        )
        self.assertIsNone(project_scoped_has_permission(a_in, "read", user=self.sup))
        self.assertFalse(project_scoped_has_permission(b_only, "read", user=self.sup))
        self.assertIsNone(project_scoped_has_permission(b_only, "read", user=self.mgr))
