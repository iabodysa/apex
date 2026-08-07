// Copyright (c) 2026, afmcoltd
frappe.query_reports["Trip Start Register"] = {
	filters: [
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
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Started", "Completed", "Cancelled"].join("\n"),
		},
	],
};
