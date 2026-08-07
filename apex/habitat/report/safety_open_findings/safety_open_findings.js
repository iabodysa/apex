// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Safety Open Findings"] = {
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
			options: ["", "High", "Medium", "Low"].join("\n"),
		},
		{
			fieldname: "execution_status",
			label: __("Result"),
			fieldtype: "Select",
			options: ["", "Excellent", "Good", "Average", "Poor", "Not Done"].join("\n"),
		},
	],
};
