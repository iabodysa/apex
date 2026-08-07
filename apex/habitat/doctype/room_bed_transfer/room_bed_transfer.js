// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Room Bed Transfer", {
	setup: function(frm) {
		frm.set_query("to_bed", function() {
			if (!frm.doc.to_room) {
				return {};
			}
			return {
				filters: {
					"room": frm.doc.to_room,
					"status": ["!=", "Occupied"]
				}
			};
		});
	},

	refresh(frm) {
	},

	to_room(frm) {
		frm.set_value("to_bed", "");
	}
});
