// Copyright (c) 2026, afmcoltd

frappe.query_reports["Vehicle Handover Register"] = {
	filters: [
		{
			fieldname: "vehicle",
			label: __("Vehicle"),
			fieldtype: "Link",
			options: "Salis Vehicle",
		},
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Salis Driver",
		},
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
