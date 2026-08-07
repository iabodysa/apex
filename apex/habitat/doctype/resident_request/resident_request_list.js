// Copyright (c) 2026, afmcoltd

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

const ARR_TRIAGE_NEXT = {
	"New": "Triaged",
	"Triaged": "In Progress",
	"In Progress": "Waiting Evidence",
	"Waiting Evidence": "In Progress",
};

frappe.listview_settings["Resident Request"] = {
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
				method: "apex.habitat.doctype.resident_request.resident_request.advance_triage_status",
				args: { name: doc.name, to_status: to_status },
				freeze: true,
				callback(r) {
					if (r.exc || !r.message || !r.message.changed) {
						return;
					}
					frappe.show_alert({
						message: __("{0} moved to {1}", [doc.name, __(r.message.status)]),
						indicator: "green",
					});
					cur_list && cur_list.refresh();
				},
				error() {
					frappe.show_alert({
						message: __("Could not advance the request. Please try again."),
						indicator: "red",
					});
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
					method: "apex.habitat.doctype.resident_request.resident_request.bulk_triage",
					args: { names: names },
					freeze: true,
					freeze_message: __("Triaging requests..."),
					callback(r) {
						if (r.exc || !r.message) {
							return;
						}
						if (r.message.queued) {
							frappe.show_alert({
								message: __("Triaging {0} requests in the background...", [r.message.total]),
								indicator: "blue",
							});
						} else {
							frappe.show_alert({
								message: __("{0} of {1} marked Triaged", [r.message.advanced, r.message.total]),
								indicator: "green",
							});
						}
						listview.clear_checked_items();
						listview.refresh();
					},
					error() {
						frappe.show_alert({
							message: __("Could not triage the requests. Please try again."),
							indicator: "red",
						});
					},
				});
			},
			false
		);
	},
};
