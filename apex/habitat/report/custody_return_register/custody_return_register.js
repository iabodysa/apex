// Copyright (c) 2026, afmcoltd

frappe.query_reports["Custody Return Register"] = {
	filters: [
		apex.report_filters.building(),
		{
			fieldname: "returned_by_employee",
			label: __("Returned By"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "custody_issue",
			label: __("Against Issue"),
			fieldtype: "Link",
			options: "Custody Issue",
		},
		{
			fieldname: "chargeable_only",
			label: __("Damaged or Lost Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
