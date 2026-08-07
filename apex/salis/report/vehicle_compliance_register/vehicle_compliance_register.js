// Copyright (c) 2026, afmcoltd
frappe.query_reports["Vehicle Compliance Register"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Valid", "Expiring Soon", "Expired"].join("\n"),
		},
		{
			fieldname: "from_date",
			label: __("Expiry From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Expiry To Date"),
			fieldtype: "Date",
		},
	],
};
