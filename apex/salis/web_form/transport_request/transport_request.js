// Copyright (c) 2026, afmcoltd
frappe.web_form.after_load = function () {
	apex.web_form.adopt_url_token("site_token");
};

frappe.web_form.after_save = function (doc) {
	apex.web_form.show_tracking_code(doc, {
		id: "salis-tracking-code",
		heading: __("Transport request submitted successfully."),
	});
};
