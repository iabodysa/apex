// Copyright (c) 2026, afmcoltd
frappe.query_reports["Cost Recovery Aging"] = {
	filters: [
		apex.report_filters.company(),
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Acknowledged", "Approved", "Recovered", "Waived", "Rejected"].join("\n"),
		},
		{
			fieldname: "recovery_type",
			label: __("Recovery Type"),
			fieldtype: "Select",
			options: ["", "Vehicle Damage", "Fuel Misuse", "Custody Loss", "Fine / Violation", "Other"].join("\n"),
		},
		apex.report_filters.vehicle(),
		apex.report_filters.driver(),
		apex.report_filters.employee(),
		apex.report_filters.as_on_date({
			default: frappe.datetime.get_today(),
		}),
	],
};
