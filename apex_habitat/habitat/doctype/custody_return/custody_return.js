// Copyright (c) 2026, AFMCO and contributors
// [#ka8ulk]
frappe.ui.form.on("Custody Return", {
	refresh(frm) {
		frm.clear_custom_buttons();
		// [#g123bl]
		const has_damage = (frm.doc.items || []).some(
			(row) => ["Damaged", "Lost"].includes(row.condition_on_return)
		);
		if (frm.doc.docstatus === 1 && has_damage) {
			frm.add_custom_button(__("Create Damage Assessment"), function () {
				frappe.model.open_mapped_doc({
					method: "apex_habitat.habitat.doctype.custody_return.custody_return.make_damage_assessment",
					frm: frm,
				});
			});
		}
	}
});
