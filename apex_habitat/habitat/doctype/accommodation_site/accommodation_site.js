// Client-side script for Accommodation Site
frappe.ui.form.on("Accommodation Site", {
	refresh(frm) {
		// Native Address (Address DocType via Dynamic Link): render the address list
		// for saved sites; city and district remain visible as structured location fields.
		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			frappe.contacts.render_address_and_contact(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}
	}
});
