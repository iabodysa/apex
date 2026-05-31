// Client-side script for Temporary Worker
frappe.ui.form.on("Temporary Worker", {
	window_days(frm) {
		// Mirror the server-side computation so the supervisor sees the expiry
		// update immediately. The controller is still authoritative on save.
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
