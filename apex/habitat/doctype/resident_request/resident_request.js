// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Resident Request", {
	setup(frm) {
		frm.set_query("room", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("bed", () => ({
			filters: {
				...(frm.doc.room ? { room: frm.doc.room } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		_update_priority_indicator(frm);

		const convertible = [
			"Maintenance", "Water", "Electrical", "AC", "Plumbing",
			"Cleaning", "Pest Control", "Facility Item", "Safety", "Custody",
		];
		const open_target = frm.doc.target_doctype && frm.doc.target_document;
		const can_convert = !frm.is_new()
			&& !open_target
			&& convertible.includes(frm.doc.request_category)
			&& !["Resolved", "Rejected", "Closed"].includes(frm.doc.status);

		if (can_convert) {
			frm.add_custom_button(__("Convert to Document"), function () {
				frappe.call({
					method: "apex.habitat.doctype.resident_request.resident_request.convert_request",
					args: { source_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Creating target document..."),
					callback: function (r) {
						if (r.exc || !r.message) {
							return;
						}
						frappe.show_alert({
							message: __("Created {0} {1}", [
								__(r.message.target_doctype),
								r.message.target_document,
							]),
							indicator: "green",
						});
						frm.reload_doc();
						frappe.set_route("Form", r.message.target_doctype, r.message.target_document);
					},
					error: function () {
						frappe.show_alert({
							message: __("Could not create the target document. Please try again."),
							indicator: "red",
						});
					},
				});
			});
		}

		if (open_target) {
			frm.add_custom_button(__("Open Target Document"), function () {
				frappe.set_route("Form", frm.doc.target_doctype, frm.doc.target_document);
			});
		}
	},
	priority(frm) {
		_update_priority_indicator(frm);
	},
});

function _update_priority_indicator(frm) {
	frm.page.clear_indicator();

	if (frm.doc.priority === "Critical") {
		frm.page.set_indicator(__("Critical"), "red");
	} else if (frm.doc.priority === "High") {
		frm.page.set_indicator(__("High Priority"), "orange");
	}
}
