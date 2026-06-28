// Copyright (c) 2026, AFMCO and contributors
// [#n8kglt]
frappe.ui.form.on("Accommodation Checkout", {
	refresh(frm) {
		// [#g123bl]
		const departure = ["Final Exit", "End of Contract"];
		if (
			frm.doc.docstatus === 1 &&
			departure.includes(frm.doc.checkout_reason) &&
			!frm.doc.departure_transport_request
		) {
			// Offer the Salis departure hand-off (mirrors the arrival desk direction).
			frm.add_custom_button(__("Arrange Departure Transport"), () => {
				frappe.call({
					method: "apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout.create_departure_transport",
					args: { checkout: frm.doc.name },
					freeze: true,
					freeze_message: __("Raising departure transport…"),
					callback: (r) => {
						if (r.message) {
							frappe.show_alert({
								message: __("Departure Transport Request {0} raised.", [r.message]),
								indicator: "green",
							});
							frm.reload_doc();
						}
					},
				});
			});
		}
	},
});
