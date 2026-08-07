// Copyright (c) 2026, afmcoltd
frappe.query_reports["Idle Resident Detection"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "project_status",
			label: __("Project Status"),
			fieldtype: "Select",
			options: ["", "Completed", "Cancelled"],
		},
		{
			fieldname: "only_unlogged",
			label: __("Only Without an Idle Report"),
			fieldtype: "Check",
		},
	],
};
