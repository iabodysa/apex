// Copyright (c) 2026, afmcoltd

frappe.query_reports["Room Bed Transfer Register"] = {
	filters: [
		apex.report_filters.building(),
		{
			fieldname: "party_type",
			label: __("Resident Type"),
			fieldtype: "Select",
			options: ["", "Employee", "Temporary Worker"].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
