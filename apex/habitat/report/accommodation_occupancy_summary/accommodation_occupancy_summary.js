// Copyright (c) 2026, afmcoltd
frappe.query_reports["Accommodation Occupancy Summary"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
	],
};
