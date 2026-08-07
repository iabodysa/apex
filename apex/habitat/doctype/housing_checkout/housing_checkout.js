// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Housing Checkout", {
	refresh(frm) {
		frm.clear_custom_buttons();
		const departure = ["Final Exit", "End of Contract"];
		if (
			frm.doc.docstatus === 1 &&
			departure.includes(frm.doc.checkout_reason) &&
			!frm.doc.departure_transport_request
		) {
			frm.add_custom_button(__("Arrange Departure Transport"), () => {
				frappe.call({
					method: "apex.habitat.doctype.housing_checkout.housing_checkout.create_departure_transport",
					args: { checkout: frm.doc.name },
					freeze: true,
					freeze_message: __("Raising departure transport…"),
					callback: (r) => {
						if (r.exc || !r.message) {
							return;
						}
						frappe.show_alert({
							message: __("Departure Transport Request {0} raised.", [r.message]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			});
		}
	},
});
