// Copyright (c) 2026, afmcoltd

frappe.query_reports["Passenger Manifest Register"] = {
	filters: [
		{
			fieldname: "route_plan",
			label: __("Route Plan"),
			fieldtype: "Link",
			options: "Route Plan",
		},
		apex.report_filters.vehicle(),
		apex.report_filters.driver(),
		{
			fieldname: "not_boarded_only",
			label: __("Not Boarded Only"),
			fieldtype: "Check",
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
