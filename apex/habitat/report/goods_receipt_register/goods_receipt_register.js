// Copyright (c) 2026, afmcoltd

frappe.query_reports["Goods Receipt Register"] = {
	filters: [
		apex.report_filters.building(),
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
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
