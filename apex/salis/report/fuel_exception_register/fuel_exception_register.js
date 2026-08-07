// Copyright (c) 2026, AFMCO and contributors
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
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
