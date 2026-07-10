// Copyright (c) 2026, AFMCO and contributors
// [#7r0wdm]
frappe.query_reports["Fleet Payment Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "expense_type",
			label: __("Expense Type"),
			fieldtype: "Select",
			options: ["", "Fuel", "Rental", "Fine / Violation", "Sponsorship Fee", "Maintenance", "Other"].join("\n"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Pending Finance", "Approved by Finance", "Paid", "Rejected", "Cancelled"].join("\n"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
