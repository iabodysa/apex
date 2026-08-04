// Copyright (c) 2026, AFMCO and contributors
// [#hezt05]

frappe.ui.form.on("Material Transfer", {
	setup(frm) {
		frm.set_query("to_building", () => ({
			filters: {
				...(frm.doc.from_building ? { name: ["!=", frm.doc.from_building] } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus === 1 && frm.doc.status === "In Transit") {
			frm.add_custom_button(__("Mark Received"), () => {
				frappe.prompt(
					[{ fieldname: "received_date", fieldtype: "Date", label: __("Received Date"), default: frappe.datetime.get_today(), reqd: 1 }],
					(values) => {
						frappe.call({
							method: "apex.habitat.doctype.material_transfer.material_transfer.mark_received",
							args: { transfer: frm.doc.name, received_date: values.received_date },
							freeze: true,
							callback: () => frm.reload_doc(),
							error: () => {
								frappe.show_alert({
									message: __("Could not mark the transfer as received. Please try again."),
									indicator: "red",
								});
							},
						});
					},
					__("Receive Transfer"),
					__("Confirm")
				);
			}).addClass("btn-primary");
		}
	},
});
