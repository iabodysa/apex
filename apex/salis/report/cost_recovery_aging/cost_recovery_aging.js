// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Cost Recovery Aging"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Acknowledged", "Approved", "Recovered", "Waived", "Rejected"].join("\n"),
		},
		{
			fieldname: "recovery_type",
			label: __("Recovery Type"),
			fieldtype: "Select",
			options: ["", "Vehicle Damage", "Fuel Misuse", "Custody Loss", "Fine / Violation", "Other"].join("\n"),
		},
		{
			fieldname: "vehicle",
			label: __("Vehicle"),
			fieldtype: "Link",
			options: "Salis Vehicle",
		},
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Salis Driver",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "as_on_date",
			label: __("As On Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
