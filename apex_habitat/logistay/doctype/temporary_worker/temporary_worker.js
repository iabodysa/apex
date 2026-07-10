// Copyright (c) 2026, AFMCO and contributors
// [#85mm1b]
frappe.ui.form.on("Temporary Worker", {
	window_days(frm) {
		// [#tw9zet]
		if (frm.doc.arrival_date && frm.doc.window_days) {
			frm.set_value(
				"expiry_date",
				frappe.datetime.add_days(frm.doc.arrival_date, frm.doc.window_days)
			);
		}
	},

	arrival_date(frm) {
		frm.trigger("window_days");
	}
});
