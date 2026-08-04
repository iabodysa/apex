// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Rental Settlement", {
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus !== 1) {
			return;
		}
		if (frm.doc.status !== "Approved" || frm.doc.payment_request) {
			return;
		}

		frm.add_custom_button(__("Raise Payment Request"), function() {
			frappe.confirm(
				__("Raise a payment request for this settlement?"),
				function() {
					frm.call({
						method: "create_payment_request",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Raising the payment request..."),
						callback: function(r) {
							if (r.exc || !r.message) {
								return;
							}
							frm.reload_doc();
							frappe.show_alert({
								message: __("Payment Request {0} is linked to this settlement.", [r.message]),
								indicator: "green",
							});
						},
						error: function() {
							frappe.show_alert({
								message: __("Could not raise the payment request. Please try again."),
								indicator: "red",
							});
						},
					});
				}
			);
		}).addClass("btn-primary");
	},
});
