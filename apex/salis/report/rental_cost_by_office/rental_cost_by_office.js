// Copyright (c) 2026, afmcoltd
frappe.query_reports["Rental Cost by Office"] = {
	filters: [
		apex.report_filters.company(),
		{
			fieldname: "rental_office",
			label: __("Rental Office"),
			fieldtype: "Link",
			options: "Rental Office",
		},
		apex.report_filters.vehicle(),
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
