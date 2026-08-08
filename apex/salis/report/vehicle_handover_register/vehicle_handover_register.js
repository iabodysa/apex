// Copyright (c) 2026, afmcoltd

frappe.query_reports["Vehicle Handover Register"] = {
	filters: [
		apex.report_filters.vehicle(),
		apex.report_filters.driver(),
		{
			fieldname: "discrepancy_status",
			label: __("Discrepancy Status"),
			fieldtype: "Select",
			options: ["", "Clean", "Discrepancy", "Resolved"].join("\n"),
		},
		{
			fieldname: "unsigned_only",
			label: __("Unsigned Only"),
			fieldtype: "Check",
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
