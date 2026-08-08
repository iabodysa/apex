// Copyright (c) 2026, afmcoltd

frappe.query_reports["Vehicle Assignment Register"] = {
	filters: [
		apex.report_filters.vehicle(),
		apex.report_filters.driver(),
		apex.report_filters.project(),
		{
			fieldname: "include_ended",
			label: __("Include Ended Assignments"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
