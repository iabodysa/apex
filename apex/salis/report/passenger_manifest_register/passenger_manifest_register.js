// Copyright (c) 2026, afmcoltd

frappe.query_reports["Passenger Manifest Register"] = {
	filters: [
		{
			fieldname: "route_plan",
			label: __("Route Plan"),
			fieldtype: "Link",
			options: "Route Plan",
		},
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
			fieldname: "not_boarded_only",
			label: __("Not Boarded Only"),
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
