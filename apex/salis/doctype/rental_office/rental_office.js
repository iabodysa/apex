// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Rental Office", {
	refresh(frm) {
		// Native Address widget renders only on a saved doc (needs a link target).
		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			frappe.contacts.render_address_and_contact(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}
	}
});
