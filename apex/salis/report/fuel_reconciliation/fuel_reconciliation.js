// Copyright (c) 2026, AFMCO and contributors
frappe.query_reports["Fuel Reconciliation"] = {
	filters: [
		{
			fieldname: "vehicle",
			label: __("Vehicle"),
			fieldtype: "Link",
			options: "Salis Vehicle",
		},
		{
			fieldname: "period_month",
			label: __("Period (Month)"),
			fieldtype: "Data",
			description: __("YYYY-MM, e.g. 2026-05"),
		},
	],
};
