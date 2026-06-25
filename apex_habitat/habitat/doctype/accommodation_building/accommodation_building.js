// [#co3q2w]

function _injectFloorLayoutStyles() {
	if (document.getElementById("apex-floor-layout-style")) return;
	var style = document.createElement("style");
	style.id = "apex-floor-layout-style";
	style.textContent = [
		".apex-floor-section { margin-bottom: 18px; }",
		".apex-floor-label { font-weight: 600; font-size: 13px; margin-bottom: 8px; color: #555; }",
		".apex-room-grid { display: flex; flex-wrap: wrap; gap: 6px; }",
		".apex-room-tile {",
		"  display: inline-flex; flex-direction: column; align-items: center; justify-content: center;",
		"  width: 72px; min-height: 48px; border-radius: 5px; cursor: pointer;",
		"  font-size: 11px; font-weight: 600; color: #fff; padding: 4px 3px; text-align: center;",
		"  border: 1px solid rgba(0,0,0,0.10); box-shadow: 0 1px 2px rgba(0,0,0,0.08);",
		"  transition: opacity 0.15s;",
		"}",
		".apex-room-tile:hover { opacity: 0.85; }",
		".apex-room-tile.color-green  { background: #4caf50; }",
		".apex-room-tile.color-orange { background: #ff9800; }",
		".apex-room-tile.color-red    { background: #f44336; }",
		".apex-room-tile.color-grey   { background: #9e9e9e; }",
		".apex-room-occ { font-size: 10px; font-weight: 400; margin-top: 2px; opacity: 0.92; }",
		".apex-layout-summary { display: flex; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }",
		".apex-legend-item { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #555; }",
		".apex-legend-dot { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }",
	].join("\n");
	document.head.appendChild(style);
}

function _renderFloorLayout(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "apex_habitat.habitat.api.building_dashboard.get_building_layout",
		args: { building: frm.doc.name },
		callback: function (r) {
			if (r.exc || !r.message) return;
			var data = r.message;

			_injectFloorLayoutStyles();

			var wrapper = frm.get_field("floor_layout_html").$wrapper;
			wrapper.empty();

			// [#i35f5h]
			var s = data.summary;
			var legendHtml = [
				'<div class="apex-layout-summary">',
				'<div class="apex-legend-item"><span class="apex-legend-dot" style="background:#4caf50"></span>',
				__("Available: {0}", [s.available]), '</div>',
				'<div class="apex-legend-item"><span class="apex-legend-dot" style="background:#ff9800"></span>',
				__("Partial / Attention: {0}", [s.partial]), '</div>',
				'<div class="apex-legend-item"><span class="apex-legend-dot" style="background:#f44336"></span>',
				__("Full: {0}", [s.full]), '</div>',
				'<div class="apex-legend-item"><span class="apex-legend-dot" style="background:#9e9e9e"></span>',
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
						frappe.set_route("Form", "Accommodation Room", room.name);
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
	// [#5bdnvg]
	const wrapper = frm.get_field("address_html").$wrapper;
	wrapper.empty();

	// Always ask the server: it resolves the building's own Address (Link or legacy
	// Dynamic Link) then the Site, so a legacy own-address shows even with no Site set.
	frappe.call({
		method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.get_site_address",
		args: {
			building_name: frm.doc.name,
			site: frm.doc.site,
			building_address: frm.doc.building_address,
		},
		callback: function (r) {
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
		method: "apex_habitat.habitat.api.building_dashboard.get_building_metrics",
		args: { building: frm.doc.name },
		callback: function (r) {
			if (r.exc || !r.message) return;
			const m = r.message;
			frm.dashboard.reset();
			// [#384474]
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

		// [#qeq1h4]
		if (!frm.is_new()) {
			_renderFloorLayout(frm);
		}

		// [#hyf59p]
		frm.toggle_display("address_html", !frm.is_new());
		if (!frm.is_new()) {
			_renderSiteAddress(frm);
		}

		// [#msjhhk]
		const colors = {
			"Active": "green",
			"Inactive": "grey",
			"Under Renovation": "orange",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}

		// [#ob62bi]
		if (!frm.is_new()) {
			frm.add_custom_button(__("Setup Rooms"), function () {
				frappe.set_route("room-setup", frm.doc.name);
			});

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
			});
		}
	},

	accommodation_type(frm) {
		_toggleFloorFields(frm);
	},

	site(frm) {
		// [#t62uep]
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
		// [#249zyk]
		frappe.set_route("room-setup", frm.doc.name);
	},
});
