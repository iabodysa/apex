// Copyright (c) 2026, afmcoltd
frappe.query_reports["Fuel Claim Register"] = {
	filters: [
		apex.report_filters.project(),
		apex.report_filters.vehicle(),
		apex.report_filters.period_month(),
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Submitted to Movement", "Reconciled", "Approved", "Disputed", "Closed"].join("\n"),
		},
	],
};
