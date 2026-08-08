// Copyright (c) 2026, afmcoltd
frappe.query_reports["Fuel Exception Register"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Under Investigation", "Evidence Required", "Resolved", "Rejected", "Closed"].join("\n"),
		},
		{
			fieldname: "exception_type",
			label: __("Exception Type"),
			fieldtype: "Select",
			options: ["", "Over-Consumption", "GPS Mismatch", "Duplicate Claim", "Suspected Fraud", "Quota Dispute", "Other"].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
