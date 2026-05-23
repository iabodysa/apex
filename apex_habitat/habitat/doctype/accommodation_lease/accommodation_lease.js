frappe.ui.form.on("Accommodation Lease", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Regenerate Payment Schedule"), () => {
				frappe.confirm(
					__("This will clear and rebuild the entire payment schedule. Continue?"),
					() => {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_lease.accommodation_lease.regenerate_schedule",
							args: { name: frm.doc.name },
							callback(r) {
								frappe.show_alert({
									message: __("{0} payment rows generated.", [r.message]),
									indicator: "green",
								});
								frm.reload_doc();
							},
						});
					}
				);
			}, __("Actions"));
		}
	},

	first_payment_date(frm) {
		_hint_schedule(frm);
	},

	billing_cycle(frm) {
		_hint_schedule(frm);
	},
});

function _hint_schedule(frm) {
	if (frm.is_new() && frm.doc.first_payment_date && frm.doc.billing_cycle) {
		frappe.show_alert({
			message: __("Payment schedule will be generated automatically on first save."),
			indicator: "blue",
		});
	}
}
