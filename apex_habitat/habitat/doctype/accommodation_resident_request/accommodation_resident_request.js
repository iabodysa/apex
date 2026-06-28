// Copyright (c) 2026, AFMCO and contributors
// [#lhs0n9]
frappe.ui.form.on("Accommodation Resident Request", {
	refresh(frm) {
		_update_priority_indicator(frm);

		// [#csgsrv]
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
					method: "apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request.convert_request",
					args: { source_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Creating target document..."),
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({
								message: __("Created {0} {1}", [
									__(r.message.target_doctype),
									r.message.target_document,
								]),
								indicator: "green",
							});
							frm.reload_doc();
							frappe.set_route("Form", r.message.target_doctype, r.message.target_document);
						}
					},
				});
			});
		}

		// [#hg0vmo]
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

// Phone-friendly triage list view: status colour-coding, a priority chip, a
// one-tap status-advance button per row, and a bulk "Mark Triaged" action. The
// allowed next state and its guards live server-side (advance_triage_status).
const ARR_STATUS_COLORS = {
	"New": "red",
	"Triaged": "orange",
	"Assigned": "blue",
	"In Progress": "blue",
	"Waiting Evidence": "yellow",
	"Resolved": "green",
	"Rejected": "gray",
	"Closed": "darkgray",
};

// Mirrors _TRIAGE_NEXT in the controller — the only one-tap advances (targets
// that need no extra field). Other states route to the form.
const ARR_TRIAGE_NEXT = {
	"New": "Triaged",
	"Triaged": "In Progress",
	"In Progress": "Waiting Evidence",
	"Waiting Evidence": "In Progress",
};

frappe.listview_settings["Accommodation Resident Request"] = {
	add_fields: ["status", "priority"],

	get_indicator(doc) {
		const color = ARR_STATUS_COLORS[doc.status] || "gray";
		return [__(doc.status), color, "status,=," + doc.status];
	},

	formatters: {
		priority(value) {
			if (!value) {
				return "";
			}
			const tones = { "Critical": "red", "High": "orange", "Medium": "blue", "Low": "gray" };
			const tone = tones[value] || "gray";
			return `<span class="indicator-pill ${tone}">${__(value)}</span>`;
		},
	},

	button: {
		show(doc) {
			return !!ARR_TRIAGE_NEXT[doc.status];
		},
		get_label(doc) {
			return __("Move to {0}", [__(ARR_TRIAGE_NEXT[doc.status])]);
		},
		get_description(doc) {
			return __("Advance this request to {0}", [__(ARR_TRIAGE_NEXT[doc.status])]);
		},
		action(doc) {
			const to_status = ARR_TRIAGE_NEXT[doc.status];
			if (!to_status) {
				return;
			}
			frappe.call({
				method: "apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request.advance_triage_status",
				args: { name: doc.name, to_status: to_status },
				freeze: true,
				callback(r) {
					if (r.message && r.message.changed) {
						frappe.show_alert({
							message: __("{0} moved to {1}", [doc.name, __(r.message.status)]),
							indicator: "green",
						});
						cur_list && cur_list.refresh();
					}
				},
			});
		},
	},

	onload(listview) {
		listview.page.add_actions_menu_item(
			__("Mark Triaged"),
			() => {
				const names = listview.get_checked_items(true);
				if (!names.length) {
					frappe.msgprint(__("Select one or more New requests first."));
					return;
				}
				frappe.call({
					method: "apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request.bulk_triage",
					args: { names: names },
					freeze: true,
					freeze_message: __("Triaging requests..."),
					callback(r) {
						if (r.message) {
							frappe.show_alert({
								message: __("{0} of {1} marked Triaged", [r.message.advanced, r.message.total]),
								indicator: "green",
							});
							listview.clear_checked_items();
							listview.refresh();
						}
					},
				});
			},
			false
		);
	},
};
