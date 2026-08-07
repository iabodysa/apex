// Copyright (c) 2026, AFMCO and contributors

frappe.query_reports["Resident Request Register"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: ["", "Low", "Medium", "High", "Critical"],
		},
		{
			fieldname: "assigned_to",
			label: __("Assigned To"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "unassigned_only",
			label: __("Unassigned Only"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_settled",
			label: __("Include Settled Requests"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
