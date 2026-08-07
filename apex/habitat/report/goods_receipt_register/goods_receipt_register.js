// Copyright (c) 2026, afmcoltd

frappe.query_reports["Goods Receipt Register"] = {
	filters: [
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Received", "Handed Over"].join("\n"),
		},
		{
			fieldname: "item_type",
			label: __("Item Type"),
			fieldtype: "Select",
			options: ["", "Custody Article", "Maintenance Material"].join("\n"),
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
