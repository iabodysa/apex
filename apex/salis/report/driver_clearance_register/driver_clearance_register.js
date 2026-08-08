// Copyright (c) 2026, afmcoltd
frappe.query_reports["Driver Clearance Register"] = {
	filters: [
		apex.report_filters.driver(),
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "In Progress", "Cleared", "Blocked", "Cancelled"].join("\n"),
		},
		{
			fieldname: "clearance_reason",
			label: __("Clearance Reason"),
			fieldtype: "Select",
			options: ["", "Resignation", "Transfer", "Termination", "End of Assignment"].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
