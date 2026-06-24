frappe.web_form.after_load = function () {
	// Pre-fill the Custody Issue from the shared ?issue= link, if present.
	var issue = new URLSearchParams(window.location.search).get("issue");
	if (issue) {
		frappe.web_form.set_value("custody_issue", issue);
	}
	if (!frappe.web_form.get_value("confirmation_method")) {
		frappe.web_form.set_value("confirmation_method", "Confirmed Receipt");
	}
};
