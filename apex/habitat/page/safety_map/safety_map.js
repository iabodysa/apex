// Copyright (c) 2026, afmcoltd

frappe.pages["safety-map"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Safety Map"),
		single_column: true,
	});

	const sm = new SafetyMap(page);
	sm.setup();
};

class SafetyMap {
	constructor(page) {
		this.page = page;
		this.building = null;
		this.data = null;
	}

	setup() {
		this.$container = $('<div class="sm-map"></div>').appendTo(this.page.main);
		this._render_empty(__("Select a building to load the map."));
		this._setup_controls();
	}

	_setup_controls() {
		this.building_field = this.page.add_field({
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
			change: () => {
				const val = this.building_field.get_value();
				if (val && val !== this.building) {
					this.building = val;
					this.refresh();
				} else if (!val && this.building) {
					this.building = null;
					this.data = null;
					this._render_empty(__("Select a building to load the map."));
				}
			},
		});

		this.page.set_primary_action(
			__("Refresh Map"),
			() => {
				if (this.building) {
					this.refresh();
				} else {
					frappe.show_alert({
						message: __("Select a building to load the map."),
						indicator: "orange",
					});
				}
			},
			"refresh"
		);
	}

	refresh() {
		if (!this.building) return;
		// The building this response belongs to. Switching buildings quickly could land the
		// OLDER response last and paint the previous building's map under the new name.
		const requested = this.building;
		this._render_loading();
		frappe.call({
			method: "apex.habitat.api.safety_map.get_safety_map",
			args: { building: requested },
			callback: (r) => {
				if (this.building !== requested) return;
				if (r.exc || !r.message) {
					this._render_error(
						__("Could not load the safety map. Please try again."),
						() => this.refresh()
					);
					return;
				}
				this.data = r.message;
				this._render_map();
			},
			error: () => {
				if (this.building !== requested) return;
				this._render_error(
					__("Could not load the safety map. Please try again."),
					() => this.refresh()
				);
			},
		});
	}

	_render_empty(message) {
		this.$container.empty();
		$('<div class="sm-empty text-muted"></div>').text(message).appendTo(this.$container);
	}

	_render_loading() {
		this.$container.empty();
		const $skel = $('<div class="sm-skeleton" aria-busy="true"></div>').appendTo(this.$container);
		$('<div class="skeleton-block"></div>').appendTo($skel);
		const $grid = $('<div class="sm-grid"></div>').appendTo($skel);
		for (let i = 0; i < 8; i++) {
			$('<div class="skeleton-block"></div>').appendTo($grid);
		}
		$('<div class="sm-empty text-muted"></div>')
			.text(__("Loading map…"))
			.appendTo(this.$container);
	}

	_render_error(message, retry) {
		this.$container.empty();
		const $err = $('<div class="sm-error"></div>')
			.css({ "text-align": "center", "padding-block": "var(--padding-xl, 30px)" })
			.appendTo(this.$container);
		$('<div class="sm-error-msg"></div>').css("margin-block-end", "var(--margin-sm, 10px)").text(message).appendTo($err);
		$('<button class="btn btn-sm btn-default sm-error-retry"></button>')
			.text(__("Retry"))
			.on("click", () => retry && retry())
			.appendTo($err);
	}

	_render_map() {
		const data = this.data;
		this.$container.empty();

		const $summary = $('<div class="sm-summary"></div>').appendTo(this.$container);
		$('<span class="sm-summary-title"></span>')
			.text(data.building_title || data.building)
			.appendTo($summary);

		const s = data.summary || {};
		$('<span class="sm-summary-counts"></span>')
			.text(
				__("{0} rooms — {1} red, {2} amber", [
					s.total_rooms || 0,
					s.red || 0,
					s.amber || 0,
				])
			)
			.appendTo($summary);

		if (data.has_recent_damage) {
			$('<div class="sm-damage-banner"></div>')
				.text(__("Recent damage assessments: {0}", [data.recent_damage_count || 0]))
				.appendTo(this.$container);
		}

		if (!data.floors || !data.floors.length) {
			this._render_empty(__("No open safety or maintenance signals for this building."));
			return;
		}

		data.floors.forEach((floor) => {
			const $floor = $('<div class="sm-floor"></div>').appendTo(this.$container);
			$('<div class="sm-floor-header"></div>').text(floor.floor_label).appendTo($floor);

			const $grid = $('<div class="sm-grid"></div>').appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				this._render_room_tile(room).appendTo($grid);
			});

			if (floor.common_zone) {
				this._render_zone_tile(floor).appendTo($grid);
			}
		});
	}

	_render_room_tile(room) {
		const $tile = $(
			`<div class="sm-room sm-room--${room.signal}" tabindex="0" role="button"></div>`
		);
		$('<div class="sm-room-number"></div>')
			.text(`${__("Room")} ${room.room_number || room.room}`)
			.appendTo($tile);

		if (room.has_open_maintenance) {
			$('<div class="sm-room-badge"></div>')
				.text(`${__("Open Maintenance")} · ${room.maintenance_count}`)
				.appendTo($tile);
		} else {
			$('<div class="sm-room-badge sm-room-badge--ok"></div>')
				.text(__("Clear"))
				.appendTo($tile);
		}

		const handler = () => this._open_safety_round();
		$tile.on("click", handler);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
		return $tile;
	}

	_render_zone_tile(floor) {
		const zone = floor.common_zone;
		const $tile = $('<div class="sm-zone" tabindex="0" role="button"></div>');
		$('<div class="sm-zone-icon"></div>').text("◇").appendTo($tile);
		$('<div class="sm-zone-label"></div>').text(zone.zone_label).appendTo($tile);

		const handler = () => this._open_safety_round();
		$tile.on("click", handler);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
		return $tile;
	}

	_open_safety_round() {
		if (!this.building) return;
		frappe.new_doc("Safety Round", { building: this.building });
	}
}
