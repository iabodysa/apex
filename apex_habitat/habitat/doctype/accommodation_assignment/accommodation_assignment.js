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
		// DocType client lifecycle hook
	},

	building(frm) {
		frm.set_value("room", "");
		frm.set_value("bed", "");
	},

	room(frm) {
		frm.set_value("bed", "");
	}
});
