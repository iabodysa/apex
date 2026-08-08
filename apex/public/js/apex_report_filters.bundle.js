// Copyright (c) 2026, afmcoltd

frappe.provide("apex.report_filters");

Object.assign(apex.report_filters, {
	field(fieldname, label, fieldtype, extra) {
		return Object.assign({ fieldname, label, fieldtype }, extra || {});
	},

	link(fieldname, label, options, extra) {
		return Object.assign({ fieldname, label, fieldtype: "Link", options }, extra || {});
	},

	building(extra) {
		return apex.report_filters.link("building", __("Building"), "Building", extra);
	},

	company(extra) {
		return apex.report_filters.link("company", __("Company"), "Company", {
			default: frappe.defaults.get_user_default("Company"),
			...(extra || {}),
		});
	},

	project(extra) {
		return apex.report_filters.link("project", __("Project"), "Project", extra);
	},

	cost_center(extra) {
		return apex.report_filters.link("cost_center", __("Cost Center"), "Cost Center", extra);
	},

	employee(extra) {
		return apex.report_filters.link("employee", __("Employee"), "Employee", extra);
	},

	vehicle(extra) {
		return apex.report_filters.link("vehicle", __("Vehicle"), "Salis Vehicle", extra);
	},

	driver(extra) {
		return apex.report_filters.link("driver", __("Driver"), "Salis Driver", extra);
	},

	from_date(extra) {
		return apex.report_filters.field("from_date", __("From Date"), "Date", extra);
	},

	to_date(extra) {
		return apex.report_filters.field("to_date", __("To Date"), "Date", extra);
	},

	as_on_date(extra) {
		return apex.report_filters.field("as_on_date", __("As On Date"), "Date", {
			default: frappe.datetime.get_today(),
			...(extra || {}),
		});
	},

	period_month(extra) {
		return apex.report_filters.field("period_month", __("Period (Month)"), "Data", {
			description: __("YYYY-MM, e.g. 2026-05"),
			...(extra || {}),
		});
	},
});
