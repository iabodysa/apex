// Client-side script for Accommodation Building
function _toggleFloorFields(frm) {
	const isApartment = frm.doc.accommodation_type === "Apartment";
	frm.set_df_property("total_floors", "hidden", isApartment ? 1 : 0);
}

function _renderBuildingDashboard(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "apex_habitat.habitat.api.building_dashboard.get_building_metrics",
		args: { building: frm.doc.name },
		callback: function (r) {
			if (r.exc || !r.message) return;
			const m = r.message;
			frm.dashboard.reset();
			// reset() hides the native Connections (links_area); re-render them so the
			// linked-document groups (Rooms, Beds, Leases, Residents, ...) still appear.
			frm.dashboard.render_links();
			frm.dashboard.add_indicator(__("Active Occupants: {0}", [m.active_occupants]),
				m.active_occupants ? "blue" : "gray");
			frm.dashboard.add_indicator(__("Open Maintenance: {0}", [m.open_maintenance]),
				m.open_maintenance ? "orange" : "green");
			frm.dashboard.add_indicator(__("Open Custody Issues: {0}", [m.open_custody]),
				m.open_custody ? "orange" : "green");
			if (m.labels && m.labels.length) {
				frm.dashboard.add_chart({
					title: __("Occupancy % Trend"),
					type: "line",
					data: {
						labels: m.labels,
						datasets: [{ name: __("Occupancy %"), values: m.occupancy }],
					},
				});
			}
		},
	});
}

frappe.ui.form.on("Accommodation Building", {
	refresh(frm) {
		_toggleFloorFields(frm);
		_renderBuildingDashboard(frm);

		// Native Address (Address DocType via Dynamic Link): render the address list
		// for saved buildings; the legacy free-text address field is hidden.
		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			frappe.contacts.render_address_and_contact(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}

		// Status indicator
		const colors = {
			"Active": "green",
			"Inactive": "grey",
			"Under Renovation": "orange",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}

		// Setup button group (only for saved documents)
		if (!frm.is_new()) {
			frm.add_custom_button(__("Setup Rooms"), function () {
				frappe.set_route("room-setup", frm.doc.name);
			}, __("Setup"));

			frm.add_custom_button(__("Generate Safety Setup"), function () {
				frappe.confirm(
					__("Are you sure you want to generate safety setup templates for this building?"),
					function () {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_safety_setup",
							args: { building_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating Safety Setup…"),
							callback: function (r) {
								if (!r.exc) frm.reload_doc();
							},
							error: function () {
								frappe.show_alert({
									message: __("Could not complete the generation. Please try again."),
									indicator: "red",
								});
							}
						});
					}
				);
			}, __("Setup"));
		}
	},

	accommodation_type(frm) {
		_toggleFloorFields(frm);
	},
});
