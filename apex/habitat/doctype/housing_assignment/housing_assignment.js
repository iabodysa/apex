// Copyright (c) 2026, AFMCO and contributors
// [#3nt923]

// Building / Room / Bed carry NO change handler on purpose. fetch_from already ties
// them upward (room <- bed.room, building <- room.building), so clearing a child on a
// parent change closed a loop: form.js:294 re-validates the Link on every model write,
// and the Room control's validate("") writes "" into its fetch target `building`
// (link.js:762) — the value just picked. set_query still narrows downward, and
// housing_assignment.py:180-191 refuses a mismatched pair on save.
frappe.ui.form.on("Housing Assignment", {
	setup: function(frm) {
		frm.set_query("room", function() {
			if (!frm.doc.building) {
				return {};
			}
			return {
				filters: {
					"building": frm.doc.building
				}
			};
		});

		frm.set_query("bed", function() {
			if (!frm.doc.room) {
				return {};
			}
			return {
				filters: {
					"room": frm.doc.room,
					"status": ["!=", "Occupied"]
				}
			};
		});
	},

	refresh(frm) {
		frm.clear_custom_buttons();
		// [#dsopww]
		if (!frm.is_new() && frm.doc.employee) {
			frm.add_custom_button(__("Issue Masar Link"), () => {
				frappe.call({
					method: "apex.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
					args: { employee: frm.doc.employee, regenerate: 0 },
					freeze: true,
					freeze_message: __("Issuing worker link…"),
					callback: (r) => {
						if (r.exc || !r.message) {
							return;
						}
						// [#jt1dyc]
						apex.masar.show_worker_link_dialog(r.message);
					},
					error: () => {
						frappe.show_alert({
							message: __("Could not issue the worker link. Please try again."),
							indicator: "red",
						});
					},
				});
			});
		}
	}
});
