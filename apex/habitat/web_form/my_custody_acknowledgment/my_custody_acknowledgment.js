// Copyright (c) 2026, AFMCO and contributors
frappe.web_form.after_load = function () {
	var issue = new URLSearchParams(window.location.search).get("issue");
	if (issue) {
		frappe.web_form.set_value("custody_issue", issue);
	}
	if (!frappe.web_form.get_value("confirmation_method")) {
		frappe.web_form.set_value("confirmation_method", "Confirmed Receipt");
	}
};
