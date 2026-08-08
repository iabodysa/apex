// Copyright (c) 2026, afmcoltd
frappe.query_reports["Rental Settlement Register"] = {
	filters: [
		{
			fieldname: "rental_office",
			label: __("Rental Office"),
			fieldtype: "Link",
			options: "Rental Office",
		},
		apex.report_filters.company(),
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Data",
		},
		apex.report_filters.period_month(),
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
