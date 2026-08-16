from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.utils import getdate
from hrms.hr.doctype.employee_advance import employee_advance as native_advance
from hrms.payroll.doctype.additional_salary import (
    additional_salary as native_additional_salary,
)
from hrms.payroll.doctype.salary_structure import (
    salary_structure as native_salary_structure,
)

from apex.apex_core.utils import employee_recovery
from apex.salis.doctype.vehicle_incident import vehicle_incident
from apex.salis.doctype.vehicle_incident.vehicle_incident import VehicleIncident

_UNSET = object()


class TestEmployeeRecovery(unittest.TestCase):
    def setUp(self):
        # frappe.flags is a LocalProxy over frappe.local, so assigning here replaces
        # it for the entire process. Restore it or every later test loses the keys
        # frappe.init seeded, starting with currently_saving, which document.insert
        # appends to on every save.
        saved = {
            name: getattr(frappe.local, name, _UNSET)
            for name in ("flags", "request")
        }
        self.addCleanup(self._restore_frappe_local, saved)
        frappe.local.flags = frappe._dict(in_test=False)
        frappe.local.request = None

    @staticmethod
    def _restore_frappe_local(saved):
        for name, value in saved.items():
            if value is _UNSET:
                delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, value)

    @patch.object(employee_recovery, "_draft_deductions", return_value=100, create=True)
    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(native_salary_structure, "make_salary_slip")
    @patch.object(employee_recovery, "frappe")
    def test_native_salary_preview_sets_prorated_net_headroom_without_persisting(
        self, frappe_mock, make_salary_slip, _links, _pending, _drafts
    ):
        frappe_mock.db.get_value.side_effect = [
            frappe._dict(
                employee="EMP-1",
                paid_amount=1000,
                claimed_amount=0,
                return_amount=0,
                docstatus=1,
                custom_source_doctype="Vehicle Incident",
                custom_source_document="VI-1",
                custom_agreed_installment=0,
            ),
            frappe._dict(salary_structure="Monthly", base=1000),
        ]
        frappe_mock.db.get_single_value.side_effect = [1, 50]
        preview = MagicMock(
            start_date="2026-08-01",
            end_date="2026-08-31",
            net_pay=350,
            gross_pay=800,
            deductions=[
                SimpleNamespace(salary_component="Structure Deduction", amount=100),
                SimpleNamespace(salary_component="Income Tax", amount=75),
                SimpleNamespace(salary_component="Loan Repayment", amount=75),
            ],
        )
        make_salary_slip.return_value = preview

        amount = employee_recovery.compute_recovery_installment("ADV-1", "2026-08-31")

        self.assertEqual(amount, 250)
        make_salary_slip.assert_called_once_with(
            "Monthly",
            employee="EMP-1",
            posting_date="2026-08-31",
            ignore_permissions=True,
            for_preview=0,
        )
        preview.insert.assert_not_called()
        preview.save.assert_not_called()
        preview.submit.assert_not_called()

    @patch.object(employee_recovery, "_draft_deductions", return_value=150, create=True)
    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(native_salary_structure, "make_salary_slip")
    @patch.object(employee_recovery, "frappe")
    def test_recovery_defers_when_native_preview_has_no_remaining_headroom(
        self, frappe_mock, make_salary_slip, _links, _pending, _drafts
    ):
        frappe_mock.db.get_value.side_effect = [
            frappe._dict(
                employee="EMP-1",
                paid_amount=500,
                claimed_amount=0,
                return_amount=0,
                docstatus=1,
                custom_source_doctype="Vehicle Incident",
                custom_source_document="VI-1",
                custom_agreed_installment=0,
            ),
            frappe._dict(salary_structure="Monthly", base=1000),
        ]
        frappe_mock.db.get_single_value.side_effect = [1, 50]
        make_salary_slip.return_value = MagicMock(
            start_date="2026-08-01",
            end_date="2026-08-31",
            net_pay=100,
            gross_pay=1000,
        )

        self.assertEqual(
            employee_recovery.compute_recovery_installment("ADV-1", "2026-08-31"),
            0,
        )
        make_salary_slip.assert_called_once()

    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(native_salary_structure, "make_salary_slip")
    @patch.object(employee_recovery, "frappe")
    def test_weekly_preview_dates_bound_draft_headroom_to_that_pay_period(
        self, frappe_mock, make_salary_slip, _links, _pending
    ):
        frappe_mock.db.get_value.side_effect = [
            frappe._dict(
                employee="EMP-1",
                paid_amount=1000,
                claimed_amount=0,
                return_amount=0,
                docstatus=1,
                custom_source_doctype="Vehicle Incident",
                custom_source_document="VI-1",
                custom_agreed_installment=0,
            ),
            frappe._dict(salary_structure="Weekly", base=1000),
        ]
        frappe_mock.db.get_single_value.side_effect = [1, 50]
        make_salary_slip.return_value = MagicMock(
            start_date="2026-08-08",
            end_date="2026-08-14",
            net_pay=300,
            gross_pay=1000,
        )

        def drafts_for_requested_period(_doctype, *, or_filters, **_kwargs):
            period = or_filters[0][2]
            if period == [getdate("2026-08-08"), getdate("2026-08-14")]:
                return [
                    frappe._dict(
                        amount=50,
                        is_recurring=0,
                        from_date=None,
                        to_date=None,
                    )
                ]
            return [
                frappe._dict(
                    amount=250,
                    is_recurring=0,
                    from_date=None,
                    to_date=None,
                )
            ]

        frappe_mock.get_all.side_effect = drafts_for_requested_period

        amount = employee_recovery.compute_recovery_installment(
            "ADV-1", "2026-08-14"
        )

        self.assertEqual(amount, 250)
        draft_query = frappe_mock.get_all.call_args
        self.assertEqual(
            draft_query.kwargs["or_filters"][0],
            [
                "payroll_date",
                "between",
                [getdate("2026-08-08"), getdate("2026-08-14")],
            ],
        )

    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(native_salary_structure, "make_salary_slip")
    @patch.object(employee_recovery, "frappe")
    def test_recovery_fails_closed_when_native_preview_cannot_be_calculated(
        self, frappe_mock, make_salary_slip, _links, _pending
    ):
        frappe_mock.db.get_value.side_effect = [
            frappe._dict(
                employee="EMP-1",
                paid_amount=500,
                claimed_amount=0,
                return_amount=0,
                docstatus=1,
                custom_source_doctype="Vehicle Incident",
                custom_source_document="VI-1",
                custom_agreed_installment=0,
            ),
            frappe._dict(salary_structure="Monthly", base=1000),
        ]
        frappe_mock.db.get_single_value.return_value = 1
        frappe_mock.logger.return_value = MagicMock()
        make_salary_slip.side_effect = RuntimeError("missing payroll period")

        self.assertEqual(
            employee_recovery.compute_recovery_installment("ADV-1", "2026-08-31"),
            0,
        )
        make_salary_slip.assert_called_once()

    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_unpaid_advance_defers_recovery(
        self, frappe_mock, _links, _pending
    ):
        frappe_mock.db.get_value.return_value = frappe._dict(
            employee="EMP-1",
            paid_amount=0,
            return_amount=0,
            docstatus=1,
            custom_source_doctype="Vehicle Incident",
            custom_source_document="VI-1",
        )

        self.assertEqual(
            employee_recovery.compute_recovery_installment(
                "ADV-1", "2026-08-31"
            ),
            0,
        )

    @patch.object(employee_recovery, "_pending_installments", return_value=200)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_existing_draft_installment_defers_cleared_balance(
        self, frappe_mock, _links, _pending
    ):
        frappe_mock.db.get_value.return_value = frappe._dict(
            employee="EMP-1",
            paid_amount=200,
            return_amount=0,
            docstatus=1,
            custom_source_doctype="Vehicle Incident",
            custom_source_document="VI-1",
        )

        self.assertEqual(
            employee_recovery.compute_recovery_installment("ADV-1", "2026-08-31"),
            0,
        )

    @patch.object(employee_recovery, "find_recovery_advance", return_value="ADV-1")
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_source_is_locked_before_duplicate_advance_check(
        self, frappe_mock, _links, find_advance
    ):
        sequence = []
        frappe_mock.logger.return_value = MagicMock()
        frappe_mock.db.get_value.side_effect = lambda *args, **kwargs: (
            sequence.append((args, kwargs)) or "VI-1"
        )
        find_advance.side_effect = lambda *args: sequence.append("find") or "ADV-1"

        result = employee_recovery.raise_recovery_advance(
            "Vehicle Incident", "VI-1", "EMP-1", 100, "Damage recovery"
        )

        self.assertEqual(result, "ADV-1")
        self.assertEqual(
            sequence[0][0][:3],
            (
                "Vehicle Incident",
                "VI-1",
                ["name", "worker_signature", "installment_amount"],
            ),
        )
        self.assertTrue(sequence[0][1]["as_dict"])
        self.assertTrue(sequence[0][1]["for_update"])
        self.assertEqual(sequence[1], "find")

    @patch.object(employee_recovery, "find_recovery_advance", return_value=None)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_vehicle_incident_snapshots_consent_and_agreed_installment_on_advance(
        self, frappe_mock, _links, _find
    ):
        frappe_mock.logger.return_value = MagicMock()

        def get_value(doctype, name_or_filters=None, fieldname=None, **kwargs):
            if doctype == "Vehicle Incident":
                return frappe._dict(
                    name="VI-1",
                    worker_signature="data:image/png;base64,SIGNED",
                    installment_amount=125,
                )
            if doctype == "Employee" and fieldname == "company":
                return "Company A"
            if doctype == "Company" and fieldname == "default_employee_advance_account":
                return "Employee Advances - A"
            if doctype == "Account":
                return "Receivable"
            if doctype == "Company" and fieldname == "default_currency":
                return "SAR"
            return None

        frappe_mock.db.get_value.side_effect = get_value
        advance = MagicMock(name="advance")
        advance.name = "ADV-1"
        frappe_mock.get_doc.return_value = advance

        result = employee_recovery.raise_recovery_advance(
            "Vehicle Incident",
            "VI-1",
            "EMP-1",
            500,
            "Damage recovery",
            posting_date="2026-08-12",
        )

        payload = frappe_mock.get_doc.call_args.args[0]
        self.assertEqual(
            payload["custom_signed_evidence"], "data:image/png;base64,SIGNED"
        )
        self.assertEqual(payload["custom_agreed_installment"], 125)
        advance.insert.assert_called_once_with(ignore_permissions=True)
        advance.submit.assert_called_once_with()
        self.assertEqual(result, "ADV-1")

    @patch.object(employee_recovery, "compute_recovery_installment", return_value=100)
    @patch.object(employee_recovery, "_recovery_component", return_value="Recovery")
    @patch.object(
        employee_recovery,
        "_salary_preview",
        return_value=(
            SimpleNamespace(start_date="2026-08-01", end_date="2026-08-31"),
            None,
        ),
    )
    @patch.object(native_advance, "create_return_through_additional_salary")
    @patch.object(employee_recovery, "frappe")
    def test_scheduler_locks_advance_and_uses_native_draft_factory(
        self, frappe_mock, native_factory, _preview, _component, _amount
    ):
        advance = SimpleNamespace(name="ADV-1", employee="EMP-1")
        installment = MagicMock(name="installment")
        installment.name = "AS-1"
        native_factory.return_value = installment
        frappe_mock.get_doc.return_value = advance
        frappe_mock.db.exists.return_value = False
        frappe_mock.logger.return_value = MagicMock()

        result = employee_recovery.schedule_recovery_deduction(
            "ADV-1", "2026-08-31"
        )

        frappe_mock.get_doc.assert_called_once_with(
            "Employee Advance", "ADV-1", for_update=True
        )
        # The whole frappe module is mocked here, so neither gate can throw and both
        # could be deleted without reddening a single case. Assert the calls themselves.
        frappe_mock.has_permission.assert_any_call(
            "Employee Advance", "read", doc=advance, throw=True
        )
        frappe_mock.has_permission.assert_any_call(
            "Additional Salary", "create", throw=True
        )
        native_factory.assert_called_once_with(advance)
        self.assertEqual(installment.salary_component, "Recovery")
        self.assertEqual(installment.amount, 100)
        self.assertEqual(installment.payroll_date, "2026-08-31")
        installment.insert.assert_called_once_with(ignore_permissions=True)
        frappe_mock.db.set_value.assert_not_called()
        self.assertEqual(result, "AS-1")

    @patch.object(employee_recovery, "_salary_preview")
    @patch.object(native_advance, "create_return_through_additional_salary")
    @patch.object(employee_recovery, "frappe")
    def test_a_denied_caller_queues_no_installment(
        self, frappe_mock, native_factory, salary_preview
    ):
        """The gate must stop the endpoint, not merely be called.

        ``schedule_recovery_deduction`` is whitelisted POST, so the two
        ``has_permission(..., throw=True)`` calls are its only authorization — and a
        MagicMock frappe cannot throw. Making the mock raise proves nothing downstream
        runs when the caller is refused.
        """
        frappe_mock.get_doc.return_value = SimpleNamespace(name="ADV-1", employee="EMP-1")
        frappe_mock.has_permission.side_effect = frappe.PermissionError

        with self.assertRaises(frappe.PermissionError):
            employee_recovery.schedule_recovery_deduction("ADV-1", "2026-08-31")

        salary_preview.assert_not_called()
        native_factory.assert_not_called()

    @patch.object(
        employee_recovery,
        "_salary_preview",
        return_value=(
            SimpleNamespace(start_date="2026-08-01", end_date="2026-08-31"),
            None,
        ),
    )
    @patch.object(employee_recovery, "frappe")
    def test_existing_draft_or_submitted_installment_is_not_duplicated(
        self, frappe_mock, _preview
    ):
        advance = SimpleNamespace(name="ADV-1", employee="EMP-1")
        frappe_mock.get_doc.return_value = advance
        frappe_mock.db.exists.return_value = "AS-1"

        result = employee_recovery.schedule_recovery_deduction(
            "ADV-1", "2026-08-31"
        )

        self.assertIsNone(result)
        duplicate_filters = frappe_mock.db.exists.call_args.args[1]
        self.assertEqual(duplicate_filters["docstatus"], ["<", 2])
        frappe_mock.get_doc.assert_called_once_with(
            "Employee Advance", "ADV-1", for_update=True
        )

    @patch.object(employee_recovery, "compute_recovery_installment", return_value=100)
    @patch.object(employee_recovery, "_recovery_component", return_value="Recovery")
    @patch.object(employee_recovery, "_salary_preview")
    @patch.object(native_advance, "create_return_through_additional_salary")
    @patch.object(employee_recovery, "frappe")
    def test_weekly_august_7_draft_does_not_dedupe_august_14_period(
        self,
        frappe_mock,
        native_factory,
        salary_preview,
        _component,
        _amount,
    ):
        advance = SimpleNamespace(name="ADV-1", employee="EMP-1")
        installment = MagicMock(name="installment")
        installment.name = "AS-14"
        frappe_mock.get_doc.return_value = advance
        frappe_mock.logger.return_value = MagicMock()
        native_factory.return_value = installment
        salary_preview.return_value = (
            SimpleNamespace(start_date="2026-08-08", end_date="2026-08-14"),
            SimpleNamespace(salary_structure="Weekly"),
        )

        def existing_august_7(_doctype, filters):
            start, end = filters["payroll_date"][1]
            return (
                "AS-07"
                if getdate(start)
                <= getdate("2026-08-07")
                <= getdate(end)
                else None
            )

        frappe_mock.db.exists.side_effect = existing_august_7

        result = employee_recovery.schedule_recovery_deduction(
            "ADV-1", "2026-08-14"
        )

        self.assertEqual(result, "AS-14")
        duplicate_filters = frappe_mock.db.exists.call_args.args[1]
        self.assertEqual(
            duplicate_filters["payroll_date"],
            [
                "between",
                [getdate("2026-08-08"), getdate("2026-08-14")],
            ],
        )

    @patch.object(employee_recovery, "compute_recovery_installment", return_value=100)
    @patch.object(employee_recovery, "_recovery_component", return_value="Recovery")
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "_", side_effect=lambda message: message)
    @patch.object(employee_recovery, "frappe")
    def test_recovery_before_submit_rejects_cancelled_stale_and_overclaim(
        self, frappe_mock, _translate, _links, _component, compute_installment
    ):
        handler = getattr(
            employee_recovery, "validate_recovery_additional_salary", None
        )
        self.assertIsNotNone(handler)
        frappe_mock.throw.side_effect = frappe.ValidationError
        row = SimpleNamespace(
            name="AS-1",
            ref_doctype="Employee Advance",
            ref_docname="ADV-1",
            amount=101,
            payroll_date="2026-08-31",
            employee="EMP-1",
            company="Company A",
            currency="SAR",
            salary_component="Recovery",
            type="Deduction",
            is_recurring=0,
            overwrite_salary_structure_amount=0,
        )

        frappe_mock.db.get_value.return_value = "Vehicle Incident"

        for advance in (
            frappe._dict(
                name="ADV-1",
                docstatus=2,
                status="Cancelled",
                employee="EMP-1",
                company="Company A",
                currency="SAR",
                custom_source_doctype="Vehicle Incident",
            ),
            frappe._dict(
                name="ADV-1",
                docstatus=1,
                status="Returned",
                employee="EMP-1",
                company="Company A",
                currency="SAR",
                custom_source_doctype="Vehicle Incident",
            ),
            frappe._dict(
                name="ADV-1",
                docstatus=1,
                status="Partly Claimed and Returned",
                employee="EMP-1",
                company="Company A",
                currency="SAR",
                custom_source_doctype="Vehicle Incident",
            ),
            frappe._dict(
                name="ADV-1",
                docstatus=1,
                status="Paid",
                employee="EMP-1",
                company="Company A",
                currency="SAR",
                custom_source_doctype="Vehicle Incident",
            ),
        ):
            with self.subTest(status=advance.status):
                frappe_mock.get_doc.return_value = advance
                with self.assertRaises(frappe.ValidationError):
                    handler(row)

        compute_installment.assert_called_with(
            "ADV-1",
            "2026-08-31",
            exclude_additional_salary="AS-1",
            locked_advance=frappe_mock.get_doc.return_value,
        )

    @patch.object(employee_recovery, "compute_recovery_installment", return_value=100)
    @patch.object(employee_recovery, "_recovery_component", return_value="Recovery")
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "_", side_effect=lambda message: message)
    @patch.object(employee_recovery, "frappe")
    def test_before_submit_rejects_mismatched_recovery_contract_before_native_mutation(
        self,
        frappe_mock,
        _translate,
        _links,
        _component,
        compute_installment,
    ):
        frappe_mock.throw.side_effect = frappe.ValidationError
        frappe_mock.db.get_value.return_value = "Vehicle Incident"
        advance = frappe._dict(
            name="ADV-1",
            employee="EMP-A",
            company="Company A",
            currency="SAR",
            return_amount=40,
            docstatus=1,
            status="Paid",
            custom_source_doctype="Vehicle Incident",
        )
        frappe_mock.get_doc.return_value = advance
        valid = {
            "name": "AS-1",
            "ref_doctype": "Employee Advance",
            "ref_docname": "ADV-1",
            "employee": "EMP-A",
            "company": "Company A",
            "currency": "SAR",
            "salary_component": "Recovery",
            "type": "Deduction",
            "amount": 50,
            "payroll_date": "2026-08-14",
            "is_recurring": 0,
            "overwrite_salary_structure_amount": 0,
        }
        attacks = {
            "employee B": {"employee": "EMP-B"},
            "earning": {"type": "Earning"},
            "wrong component": {"salary_component": "Bonus"},
            "wrong company": {"company": "Company B"},
            "wrong currency": {"currency": "USD"},
            "recurring": {"is_recurring": 1},
            "overwrite": {"overwrite_salary_structure_amount": 1},
            "missing payroll date": {"payroll_date": None},
        }

        for attack, changes in attacks.items():
            with self.subTest(attack=attack):
                row = SimpleNamespace(**(valid | changes))
                with self.assertRaises(frappe.ValidationError):
                    employee_recovery.validate_recovery_additional_salary(row)
                self.assertEqual(advance.return_amount, 40)
                frappe_mock.db.set_value.assert_not_called()
                compute_installment.assert_not_called()
                frappe_mock.throw.reset_mock()

    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "_", side_effect=lambda message: message)
    @patch.object(employee_recovery, "frappe")
    def test_before_submit_leaves_native_employee_advance_rows_untouched(
        self, frappe_mock, _translate, _links
    ):
        """A native Employee Advance — one no Apex source ever raised — is read and
        then left alone.

        The guard cannot know an advance is native without opening it, so the
        assertion is that nothing is CHANGED, not that nothing is read: the row is
        fetched under its own lock (employee_recovery.py:489, the ordering the lock
        guard pins) and the source-field check at :490 returns before any throw,
        set_value or installment computation.
        """
        frappe_mock.throw.side_effect = frappe.ValidationError
        advance = MagicMock(name="advance")
        advance.get.return_value = None
        frappe_mock.get_doc.return_value = advance
        row = SimpleNamespace(
            name="AS-NATIVE",
            ref_doctype="Employee Advance",
            ref_docname="ADV-NATIVE",
            amount=100,
            payroll_date="2026-08-31",
        )

        employee_recovery.validate_recovery_additional_salary(row)

        frappe_mock.get_doc.assert_called_once_with(
            "Employee Advance", "ADV-NATIVE", for_update=True
        )
        advance.get.assert_called_once_with(employee_recovery.SOURCE_DOCTYPE_FIELD)
        frappe_mock.throw.assert_not_called()
        frappe_mock.db.set_value.assert_not_called()

    @patch.object(vehicle_incident, "frappe")
    def test_incident_cancel_disables_and_retains_linked_draft_installments(
        self, frappe_mock
    ):
        state = frappe._dict(name="ADV-1", docstatus=1, paid_amount=0, return_amount=0)
        incident = SimpleNamespace(
            _live_recovery_advance=lambda: state,
        )
        frappe_mock.get_all.return_value = ["AS-1", "AS-2"]
        advance = MagicMock(name="advance")
        frappe_mock.get_doc.return_value = advance

        VehicleIncident._release_recovery_advance(incident)

        self.assertEqual(
            frappe_mock.db.set_value.call_args_list,
            [
                call(
                    "Additional Salary",
                    "AS-1",
                    "disabled",
                    1,
                    update_modified=False,
                ),
                call(
                    "Additional Salary",
                    "AS-2",
                    "disabled",
                    1,
                    update_modified=False,
                ),
            ],
        )
        frappe_mock.delete_doc.assert_not_called()
        advance.cancel.assert_called_once_with()

    @patch.object(native_additional_salary, "frappe")
    def test_native_additional_salary_submit_and_cancel_reverse_advance(
        self, frappe_mock
    ):
        advance = MagicMock(name="advance")
        frappe_mock.get_doc.return_value = advance
        frappe_mock.db.get_value.side_effect = [200, 300]
        installment = SimpleNamespace(
            ref_doctype="Employee Advance",
            ref_docname="ADV-1",
            amount=100,
            docstatus=1,
        )

        native_additional_salary.AdditionalSalary.update_return_amount_in_employee_advance(
            installment
        )
        installment.docstatus = 2
        native_additional_salary.AdditionalSalary.update_return_amount_in_employee_advance(
            installment
        )

        self.assertEqual(
            frappe_mock.db.set_value.call_args_list[0].args,
            ("Employee Advance", "ADV-1", "return_amount", 300),
        )
        self.assertEqual(
            frappe_mock.db.set_value.call_args_list[1].args,
            ("Employee Advance", "ADV-1", "return_amount", 200),
        )
        self.assertEqual(advance.set_status.call_count, 2)


class TestRecoveryDisabledRefusal(unittest.TestCase):
    """A person pressing Deduct, or saving a recovery Additional Salary by hand, while
    recovery is off must see a named reason -- not the silent no-op the scheduled run
    is allowed, and not a field-comparison error pointing at a document that is correct."""

    @patch.object(employee_recovery, "_")
    @patch.object(employee_recovery, "frappe")
    def test_refuses_while_disabled(self, frappe_mock, translate):
        frappe_mock.db.get_single_value.return_value = 0
        translate.side_effect = lambda message: message
        frappe_mock.throw.side_effect = frappe.ValidationError

        with self.assertRaises(frappe.ValidationError):
            employee_recovery._refuse_while_recovery_is_disabled()

        self.assertIn("Recovery is disabled", frappe_mock.throw.call_args.kwargs["title"])

    @patch.object(employee_recovery, "frappe")
    def test_does_not_refuse_while_enabled(self, frappe_mock):
        frappe_mock.db.get_single_value.return_value = 1

        employee_recovery._refuse_while_recovery_is_disabled()

        frappe_mock.throw.assert_not_called()

    @patch.object(employee_recovery, "_recovery_component", wraps=employee_recovery._recovery_component)
    @patch.object(employee_recovery, "frappe")
    def test_schedule_recovery_deduction_refuses_before_reading_the_advance(
        self, frappe_mock, component
    ):
        """The refusal has to come before any advance/component lookup, or a caller
        who only has recovery-off state to look at is sent chasing a document that
        never had a chance to be wrong."""
        frappe_mock.db.get_single_value.return_value = 0
        frappe_mock.throw.side_effect = frappe.ValidationError

        with self.assertRaises(frappe.ValidationError):
            employee_recovery.schedule_recovery_deduction("ADV-1")

        frappe_mock.get_doc.assert_not_called()
        component.assert_not_called()


if __name__ == "__main__":
    unittest.main()
