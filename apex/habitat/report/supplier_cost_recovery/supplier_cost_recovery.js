// Copyright (c) 2026, afmcoltd
frappe.query_reports["Supplier Cost Recovery"] = {
	filters: [
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				{value: 1, label: __("January")}, {value: 2, label: __("February")},
				{value: 3, label: __("March")}, {value: 4, label: __("April")},
				{value: 5, label: __("May")}, {value: 6, label: __("June")},
				{value: 7, label: __("July")}, {value: 8, label: __("August")},
				{value: 9, label: __("September")}, {value: 10, label: __("October")},
				{value: 11, label: __("November")}, {value: 12, label: __("December")},
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		apex.report_filters.project(),
		apex.report_filters.company(),
		apex.report_filters.cost_center(),
	],
};
