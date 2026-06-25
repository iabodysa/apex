frappe.query_reports["Idle Resident Candidates"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Accommodation Building",
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
