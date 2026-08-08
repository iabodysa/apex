// Copyright (c) 2026, afmcoltd

frappe.query_reports["Accommodation Stock Balance"] = {
	filters: [
		apex.report_filters.building(),
		{
			fieldname: "item_type",
			label: __("Item Type"),
			fieldtype: "Select",
			options: ["", "Custody Article", "Maintenance Material"],
		},
		apex.report_filters.employee(),
		apex.report_filters.as_on_date({
			default: frappe.datetime.get_today(),
		}),
		{
			fieldname: "show_zero_balances",
			label: __("Show Zero Balances"),
			fieldtype: "Check",
		},
	],
};
