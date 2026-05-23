// Client-side script for Room Bed Transfer
frappe.ui.form.on("Room Bed Transfer", {
	setup: function(frm) {
		// Restrict "To Bed" selection to the chosen "To Room" and only show beds that are not Occupied
		frm.set_query("to_bed", function() {
			if (!frm.doc.to_room) {
				return {}; // will return nothing or all if standard, but depends_on hides it anyway
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
		// DocType client lifecycle hook
	},

	to_room(frm) {
		// clear bed if room changes
		frm.set_value("to_bed", "");
	}
});
