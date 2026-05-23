// Client-side script for Accommodation Building
frappe.ui.form.on("Accommodation Building", {
	refresh(frm) {
		const colors = {
			"Active": "green",
			"Inactive": "grey",
			"Under Renovation": "orange",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}

		if (!frm.is_new()) {
			// Button: Generate Rooms & Beds
			frm.add_custom_button(__("Generate Rooms & Beds"), () => {
				frappe.confirm(__("Are you sure you want to generate rooms and beds from the floor plan?"), () => {
					frappe.call({
						method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
						args: {
							building_name: frm.doc.name
						},
						freeze: true,
						freeze_message: __("Generating Rooms & Beds..."),
						callback: function(r) {
							if (!r.exc) {
								frm.reload_doc();
							}
						}
					});
				});
			}, __("Actions"));

			// Button: Generate Safety Setup
			frm.add_custom_button(__("Generate Safety Setup"), () => {
				frappe.confirm(__("Are you sure you want to generate safety setup templates for this building?"), () => {
					frappe.call({
						method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_safety_setup",
						args: {
							building_name: frm.doc.name
						},
						freeze: true,
						freeze_message: __("Generating Safety Setup..."),
						callback: function(r) {
							if (!r.exc) {
								frm.reload_doc();
							}
						}
					});
				});
			}, __("Actions"));
		}
	},
});
