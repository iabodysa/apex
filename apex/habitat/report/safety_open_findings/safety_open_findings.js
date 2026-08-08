// Copyright (c) 2026, afmcoltd
frappe.query_reports["Safety Open Findings"] = {
	filters: [
		apex.report_filters.building(),
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
