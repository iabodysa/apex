// [#a5yn69]
frappe.ui.form.on("Building License", {
	refresh(frm) {
		// [#cplw07]
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Renew License"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Renew License"),
					fields: [
						{
							fieldname: "new_expiry_date",
							fieldtype: "Date",
							label: __("New Expiry Date"),
							reqd: 1,
							default: frappe.datetime.add_months(frm.doc.expiry_date || frappe.datetime.nowdate(), 12),
						},
					],
					primary_action_label: __("Renew"),
					primary_action(values) {
						frappe.call({
							method: "apex_habitat.habitat.doctype.building_license.building_license.renew",
							args: { name: frm.doc.name, new_expiry_date: values.new_expiry_date },
							freeze: true,
							callback() {
								d.hide();
								frappe.show_alert({ message: __("License renewed."), indicator: "green" });
								frm.reload_doc();
							},
						});
					},
				});
				d.show();
			});
		}
	}
});
