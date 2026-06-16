// [#dcpq47]
frappe.ui.form.on("Room Bed Transfer", {
	setup: function(frm) {
		// [#jhvhmd]
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
		// [#g123bl]
	},

	to_room(frm) {
		// [#qvjsr0]
		frm.set_value("to_bed", "");
	}
});
