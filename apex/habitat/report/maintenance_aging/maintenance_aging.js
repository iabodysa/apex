// Copyright (c) 2026, afmcoltd
frappe.query_reports["Maintenance Aging"] = {
	filters: [
		apex.report_filters.building(),
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: ["", "Critical", "High", "Medium", "Low"].join("\n"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "In Progress", "Resolved"].join("\n"),
		},
		apex.report_filters.company(),
		apex.report_filters.cost_center(),
	],
};
