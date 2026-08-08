// Copyright (c) 2026, afmcoltd
frappe.web_form.after_load = function () {
	apex.web_form.adopt_url_token("location_token");
};

frappe.web_form.after_save = function (doc) {
	apex.web_form.show_tracking_code(doc, {
		id: "habitat-tracking-code",
		heading: __("Request submitted successfully."),
	});
};
