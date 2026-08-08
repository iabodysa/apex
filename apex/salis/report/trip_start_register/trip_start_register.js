// Copyright (c) 2026, afmcoltd
frappe.query_reports["Trip Start Register"] = {
	filters: [
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Started", "Completed", "Cancelled"].join("\n"),
		},
	],
};
