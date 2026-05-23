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
					<strong>Setup Wizard:</strong> Please save the building first to unlock the Quick Setup Wizard.
				</div>
			`);
		} else {
			wrapper.html(`
				<div class="alert alert-info d-flex align-items-center justify-content-between" style="margin-bottom: 0;">
					<div>
						<strong>Setup Wizard:</strong> Use the Quick Setup Wizard to easily generate all floors, rooms, and beds in one go!
					</div>
					<div>
						<button class="btn btn-primary btn-sm btn-quick-wizard">⚡ Quick Setup Wizard</button>
						<button class="btn btn-default btn-sm ml-2 btn-generate-rooms">Generate from Table</button>
						<button class="btn btn-default btn-sm ml-2 btn-generate-safety">Generate Safety Setup</button>
					</div>
				</div>
			`);

			wrapper.find(".btn-quick-wizard").on("click", () => {
				frappe.prompt([
					{
						label: 'Number of Floors',
						fieldname: 'num_floors',
						fieldtype: 'Int',
						reqd: 1,
						default: 3
					},
					{
						label: 'Rooms per Floor',
						fieldname: 'rooms_per_floor',
						fieldtype: 'Int',
						reqd: 1,
						default: 10
					},
					{
						label: 'Beds per Room',
						fieldname: 'beds_per_room',
						fieldtype: 'Int',
						reqd: 1,
						default: 4
					}
				], (values) => {
					// Clear existing floor plan
					frm.doc.floor_plan = [];
					
					for (let i = 1; i <= values.num_floors; i++) {
						let row = frm.add_child("floor_plan");
						row.floor_number = String(i);
						row.starting_room_number = 1;
						row.room_count = values.rooms_per_floor;
						row.bed_capacity_per_room = values.beds_per_room;
						row.room_type = "Standard";
						row.generate_beds = 1;
					}
					
					frm.refresh_field("floor_plan");
					
					frappe.msgprint({
						title: __('Wizard Generating...'),
						message: __('Floor plan table populated. Saving building and generating rooms...'),
						indicator: 'green'
					});

					frm.save().then(() => {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
							args: { building_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Building all Rooms & Beds..."),
							callback: function(r) {
								if (!r.exc) {
									frappe.show_alert({message: __('Successfully generated all rooms and beds!'), indicator: 'green'});
									frm.reload_doc();
								}
							}
						});
					});

				}, 'Quick Setup Wizard', 'Build Now!');
			});

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
