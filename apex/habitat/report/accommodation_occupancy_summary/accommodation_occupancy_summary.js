// Copyright (c) 2026, AFMCO and contributors
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
