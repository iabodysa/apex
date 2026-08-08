// Copyright (c) 2026, afmcoltd
frappe.query_reports["Worker Transport Plan"] = {
	filters: [
		{
			fieldname: "request_type",
			label: __("Request Type"),
			fieldtype: "Select",
			options: ["", "Accommodation to Project Shuttle", "Inter-City Relocation", "Administrative Trip / Document Signing"].join("\n"),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "New", "Validated", "Approved", "Scheduled", "Fulfilled", "Rejected", "Cancelled"].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
