// Copyright (c) 2026, afmcoltd
frappe.query_reports["Idle Resident Detection"] = {
	filters: [
		apex.report_filters.building(),
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
