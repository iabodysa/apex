// Copyright (c) 2026, afmcoltd
frappe.query_reports["Audit Remediation Status"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Open",
				"In Progress",
				"Evidence Submitted",
				"Verified by Client",
				"Rejected by Client",
			].join("\n"),
		},
		apex.report_filters.from_date(),
		apex.report_filters.to_date(),
	],
};
