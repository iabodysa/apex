// Copyright (c) 2026, Abdullah Fahad Al-Mutairi Co. (AFMCO) and contributors
// For license information, please see license.txt

frappe.ui.form.on("Accommodation Material Transfer", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "In Transit") {
			frm.add_custom_button(__("Mark Received"), () => {
				frappe.prompt(
					[{ fieldname: "received_date", fieldtype: "Date", label: __("Received Date"), default: frappe.datetime.get_today(), reqd: 1 }],
					(values) => {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_material_transfer.accommodation_material_transfer.mark_received",
							args: { transfer: frm.doc.name, received_date: values.received_date },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					},
					__("Receive Transfer"),
					__("Confirm")
				);
			}).addClass("btn-primary");
		}
	},
});
