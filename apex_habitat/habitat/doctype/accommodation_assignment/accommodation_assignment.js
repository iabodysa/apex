// Client-side script for Accommodation Assignment
frappe.ui.form.on("Accommodation Assignment", {
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
		// Supervisor surface: issue the assigned worker's personal Masar link.
		// Only meaningful on a saved Assignment that actually has an employee.
		if (!frm.is_new() && frm.doc.employee) {
			frm.add_custom_button(__("Issue Masar Link"), () => {
				frappe.call({
					method: "apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
					args: { employee: frm.doc.employee, regenerate: 0 },
					freeze: true,
					freeze_message: __("Issuing worker link…"),
					callback: (r) => {
						if (r.message) {
							// Shared helper from
							// public/js/masar_worker_link.bundle.js (wired via
							// hooks.py app_include_js). No copy-link button on
							// the supervisor surface — that's the Arrivals Desk
							// superset.
							apex_habitat.masar.show_worker_link_dialog(r.message);
						}
					},
				});
			});
		}
	},

	building(frm) {
		frm.set_value("room", "");
		frm.set_value("bed", "");
	},

	room(frm) {
		frm.set_value("bed", "");
	}
});
