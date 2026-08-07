// Copyright (c) 2026, AFMCO and contributors

frappe.query_reports["Vehicle Assignment Register"] = {
	filters: [
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
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "include_ended",
			label: __("Include Ended Assignments"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
