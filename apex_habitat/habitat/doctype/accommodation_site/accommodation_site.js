// [#myqrhw]
frappe.ui.form.on("Accommodation Site", {
	refresh(frm) {
		// [#oe3or3]
		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			frappe.contacts.render_address_and_contact(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}
	}
});
