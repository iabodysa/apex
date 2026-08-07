// Copyright (c) 2026, afmcoltd
frappe.query_reports["Checkout Pending Clearance"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
	],
};
