// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Site", {
	refresh(frm) {
		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			frappe.contacts.render_address_and_contact(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}
	}
});
