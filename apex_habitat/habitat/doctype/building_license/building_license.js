// Client-side script for Building License
frappe.ui.form.on("Building License", {
	refresh(frm) {
		// On a draft license, offer an explicit Renew action that rolls the
		// expiry date forward and stamps Last Renewed On. A submitted license is
		// renewed by amending it with a later expiry (the controller stamps the date).
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
