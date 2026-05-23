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

		let wrapper = frm.get_field("setup_instructions_html").$wrapper;
		wrapper.empty();

		if (frm.is_new()) {
			wrapper.html(`
				<div class="alert alert-warning" style="margin-bottom: 0;">
					<strong>Setup Wizard:</strong> Please define your floor plans below and <b>save the document</b> to unlock the generation buttons.
				</div>
			`);
		} else {
			wrapper.html(`
				<div class="alert alert-info d-flex align-items-center justify-content-between" style="margin-bottom: 0;">
					<div>
						<strong>Setup Wizard:</strong> Click to auto-generate rooms, beds, and safety setups based on your building configuration.
					</div>
					<div>
						<button class="btn btn-primary btn-sm btn-generate-rooms">Generate Rooms & Beds</button>
						<button class="btn btn-default btn-sm ml-2 btn-generate-safety">Generate Safety Setup</button>
					</div>
				</div>
			`);

			wrapper.find(".btn-generate-rooms").on("click", () => {
				frappe.confirm(__("Are you sure you want to generate rooms and beds from the floor plan?"), () => {
					frappe.call({
						method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
						args: { building_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating Rooms & Beds..."),
						callback: function(r) {
							if (!r.exc) frm.reload_doc();
						}
					});
				});
			});

			wrapper.find(".btn-generate-safety").on("click", () => {
				frappe.confirm(__("Are you sure you want to generate safety setup templates for this building?"), () => {
					frappe.call({
						method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_safety_setup",
						args: { building_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating Safety Setup..."),
						callback: function(r) {
							if (!r.exc) frm.reload_doc();
						}
					});
				});
			});
		}
	},
});
