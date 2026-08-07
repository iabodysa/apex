// Copyright (c) 2026, afmcoltd

function _renderFloorLayout(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "apex.habitat.api.building_dashboard.get_building_layout",
		args: { building: frm.doc.name },
		error: function () {},
		callback: function (r) {
			if (r.exc || !r.message) return;
			var data = r.message;

			var wrapper = frm.get_field("floor_layout_html").$wrapper;
			wrapper.empty();

			var s = data.summary;
			var legendHtml = [
				'<div class="apex-layout-summary">',
				'<div class="apex-legend-item"><span class="apex-legend-dot color-green"></span>',
				__("Available: {0}", [s.available]), '</div>',
				'<div class="apex-legend-item"><span class="apex-legend-dot color-orange"></span>',
				__("Partial / Attention: {0}", [s.partial]), '</div>',
				'<div class="apex-legend-item"><span class="apex-legend-dot color-red"></span>',
				__("Full: {0}", [s.full]), '</div>',
				'<div class="apex-legend-item"><span class="apex-legend-dot color-grey"></span>',
				__("Maintenance: {0}", [s.maintenance]), '</div>',
				'</div>',
			].join("");
			wrapper.append($(legendHtml));

			if (!data.floors || !data.floors.length) {
				wrapper.append($('<p style="color:#999;font-size:13px;">' + __("No rooms found for this building.") + '</p>'));
				return;
			}

			data.floors.forEach(function (floor) {
				var section = $('<div class="apex-floor-section"></div>');
				section.append($('<div class="apex-floor-label"></div>').text(__(floor.floor_label)));
				var grid = $('<div class="apex-room-grid"></div>');

				(floor.rooms || []).forEach(function (room) {
					var occ = (room.current_occupancy != null ? room.current_occupancy : "—");
					var cap = (room.bed_capacity != null ? room.bed_capacity : "—");
					var tile = $(
						'<div class="apex-room-tile color-' + (room.room_color || "grey") + '" title="' +
						frappe.utils.escape_html(room.room_number || room.name) + '"></div>'
					);
					tile.append($('<div></div>').text(room.room_number || room.name));
					tile.append($('<div class="apex-room-occ"></div>').text(occ + "/" + cap));
					tile.on("click", function () {
						frappe.set_route("Form", "Room", room.name);
					});
					grid.append(tile);
				});

				section.append(grid);
				wrapper.append(section);
			});
		},
	});
}

function _toggleFloorFields(frm) {
	const isApartment = frm.doc.accommodation_type === "Apartment";
	frm.set_df_property("total_floors", "hidden", isApartment ? 1 : 0);
}

function _renderSiteAddress(frm) {
	const wrapper = frm.get_field("address_html").$wrapper;
	wrapper.empty();

	frappe.call({
		method: "apex.habitat.doctype.building.building.get_site_address",
		args: {
			building_name: frm.doc.name,
			site: frm.doc.site,
			building_address: frm.doc.building_address,
		},
		error: function () {},
		callback: function (r) {
			if (r.exc) return;
			wrapper.empty();
			const text = r.message;
			if (text) {
				wrapper.append($("<div></div>").text(text));
			} else {
				wrapper.append(
					$('<p class="text-muted" style="font-size:13px;"></p>').text(
						__("Select this building's address, or a Site, to show it here.")
					)
				);
			}
		},
	});
}

function _renderBuildingDashboard(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "apex.habitat.api.building_dashboard.get_building_metrics",
		args: { building: frm.doc.name },
		error: function () {},
		callback: function (r) {
			if (r.exc || !r.message) return;
			const m = r.message;
			frm.dashboard.reset();
			frm.dashboard.render_links();
			frm.dashboard.add_indicator(__("Active Occupants: {0}", [m.active_occupants]),
				m.active_occupants ? "blue" : "gray");
			frm.dashboard.add_indicator(__("Open Maintenance: {0}", [m.open_maintenance]),
				m.open_maintenance ? "orange" : "green");
			frm.dashboard.add_indicator(__("Open Custody Issues: {0}", [m.open_custody]),
				m.open_custody ? "orange" : "green");
			if (m.labels && m.labels.length) {
				frm.dashboard.render_graph({
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

frappe.ui.form.on("Building", {
	setup(frm) {
		frm.set_query("default_cost_center", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		_toggleFloorFields(frm);
		_renderBuildingDashboard(frm);

		if (!frm.is_new()) {
			_renderFloorLayout(frm);
		}

		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			_renderSiteAddress(frm);
		}

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
			frm.add_custom_button(__("Setup Rooms"), function () {
				frappe.set_route("room-setup", frm.doc.name);
			});

			frm.add_custom_button(__("Generate Safety Setup"), function () {
				frappe.confirm(
					__("Are you sure you want to generate safety setup templates for this building?"),
					function () {
						frappe.call({
							method: "apex.habitat.doctype.building.building.generate_safety_setup",
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
			});
		}
	},

	accommodation_type(frm) {
		_toggleFloorFields(frm);
	},

	site(frm) {
		if (!frm.is_new()) {
			_renderSiteAddress(frm);
		}
	},

	building_address(frm) {
		if (!frm.is_new()) {
			_renderSiteAddress(frm);
		}
	},

	edit_room_setup_btn(frm) {
		frappe.set_route("room-setup", frm.doc.name);
	},
});
