// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Vehicle Handover", {
	refresh(frm) {
		// Only show active templates in the picker.
		frm.set_query("checklist_template", function () {
			return { filters: { is_active: 1 } };
		});

		if (frm.doc.docstatus === 0 && frm.doc.checklist_template) {
			frm.add_custom_button(__("Load Checklist Template"), function () {
				frappe.call({
					method:
						"apex_habitat.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template.load_template_into_doc",
					args: { handover: frm.docname, template: frm.doc.checklist_template },
					freeze: true,
					freeze_message: __("Loading checklist..."),
					callback: function (r) {
						if (r.message) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("{0} check item(s) loaded from template {1}", [
									r.message.rows_added,
									r.message.template,
								]),
								indicator: r.message.rows_added ? "green" : "orange",
							});
						}
					},
					error: function () {
						frappe.show_alert({
							message: __("Could not load the checklist template. Please try again."),
							indicator: "red",
						});
					},
				});
			});
		}
	},
});
