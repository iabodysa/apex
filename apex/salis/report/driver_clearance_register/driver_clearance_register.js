// Copyright (c) 2026, afmcoltd
frappe.query_reports["Driver Clearance Register"] = {
	filters: [
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Salis Driver",
		},
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
