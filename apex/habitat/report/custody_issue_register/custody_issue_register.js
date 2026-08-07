// Copyright (c) 2026, AFMCO and contributors

frappe.query_reports["Custody Issue Register"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "issued_to_employee",
			label: __("Issued To"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Issued", "Returned", "Partially Returned"],
		},
		{
			fieldname: "overdue_only",
			label: __("Overdue Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
