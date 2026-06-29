// Copyright (c) 2026, AFMCO and contributors
// [#l7bpkl]

frappe.pages["safety-map"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Safety Map"),
		single_column: true,
	});

	const sm = new SafetyMap(page);
	sm.setup();
};

// Desk pages ship no stylesheet — layout is inline styles bound to native Desk
// CSS variables (theme/dark-mode aware). The signal colour keys (red danger /
// amber warning / green clear) alias the Desk colour-scale vars.
const SM_SIGNAL = {
	red: "background:var(--red-100);border-color:var(--red-500);color:var(--red-700);",
	amber: "background:var(--yellow-100);border-color:var(--orange-500);color:var(--orange-700);",
	green: "background:var(--green-100);border-color:var(--green-500);color:var(--green-700);",
};
const SM_STYLE = {
	summary:
		"display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--margin-md,15px);margin-block:var(--margin-sm,10px) var(--margin-md,15px);",
	summary_title: "font-size:18px;font-weight:600;",
	summary_counts: "font-size:var(--text-sm,12px);color:var(--text-muted);",
	damage_banner:
		"background:var(--yellow-100);border:1px solid var(--orange-500);color:var(--orange-700);border-radius:var(--border-radius-md,8px);padding:var(--padding-sm,10px) var(--padding-md,15px);margin-block-end:var(--margin-md,15px);font-size:var(--text-sm,12px);",
	floor: "margin-block-end:var(--margin-lg,20px);",
	grid: "display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:var(--margin-sm,10px);",
	tile_base:
		"border:2px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:14px 12px;min-height:86px;display:flex;flex-direction:column;justify-content:space-between;gap:6px;cursor:pointer;background:var(--card-bg);",
	zone:
		"border:1px dashed var(--border-color);border-radius:var(--border-radius-md,8px);padding:14px 12px;min-height:86px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;cursor:pointer;background:var(--subtle-fg,var(--control-bg));color:var(--text-muted);",
	room_number: "font-weight:600;font-size:var(--text-md,14px);",
	badge: "font-size:11px;font-weight:600;",
	empty: "padding-block:var(--padding-xl,30px);text-align:center;font-size:var(--text-md,14px);",
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
			options: "Accommodation Building",
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
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.safety_map.get_safety_map",
			args: { building: this.building },
			callback: (r) => {
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
				this._render_error(
					__("Could not load the safety map. Please try again."),
					() => this.refresh()
				);
			},
		});
	}

	_render_empty(message) {
		this.$container.empty();
		$('<div class="sm-empty text-muted"></div>').attr("style", SM_STYLE.empty).text(message).appendTo(this.$container);
	}

	_render_loading() {
		this.$container.empty();
		const $skel = $('<div class="sm-skeleton" aria-busy="true"></div>').appendTo(this.$container);
		// Native Frappe skeleton blocks (shimmer included) — no custom skeleton CSS.
		$('<div class="skeleton-block"></div>')
			.css({ height: "20px", "margin-block": "var(--margin-sm, 10px)" })
			.appendTo($skel);
		const $grid = $('<div></div>').attr("style", SM_STYLE.grid).appendTo($skel);
		for (let i = 0; i < 8; i++) {
			$('<div class="skeleton-block"></div>').css("height", "86px").appendTo($grid);
		}
		$('<div class="sm-empty text-muted"></div>')
			.attr("style", SM_STYLE.empty)
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

		const $summary = $('<div class="sm-summary"></div>').attr("style", SM_STYLE.summary).appendTo(this.$container);
		$('<span class="sm-summary-title"></span>')
			.attr("style", SM_STYLE.summary_title)
			.text(data.building_title || data.building)
			.appendTo($summary);

		const s = data.summary || {};
		$('<span class="sm-summary-counts"></span>')
			.attr("style", SM_STYLE.summary_counts)
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
				.attr("style", SM_STYLE.damage_banner)
				.text(__("Recent damage assessments: {0}", [data.recent_damage_count || 0]))
				.appendTo(this.$container);
		}

		if (!data.floors || !data.floors.length) {
			this._render_empty(__("No open safety or maintenance signals for this building."));
			return;
		}

		// Uppercasing + letter-spacing break Arabic shaping → drop both in RTL.
		const floor_head = frappe.utils.is_rtl()
			? "font-size:var(--text-md,14px);font-weight:600;color:var(--text-muted);margin-block-end:var(--margin-sm,10px);"
			: "font-size:var(--text-md,14px);font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;margin-block-end:var(--margin-sm,10px);";
		data.floors.forEach((floor) => {
			const $floor = $('<div class="sm-floor"></div>').attr("style", SM_STYLE.floor).appendTo(this.$container);
			$('<div class="sm-floor-header"></div>').attr("style", floor_head).text(floor.floor_label).appendTo($floor);

			const $grid = $('<div class="sm-grid"></div>').attr("style", SM_STYLE.grid).appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				this._render_room_tile(floor, room).appendTo($grid);
			});

			// [#fk2nxe]
			if (floor.common_zone) {
				this._render_zone_tile(floor).appendTo($grid);
			}
		});
	}

	_render_room_tile(floor, room) {
		const $tile = $(
			`<div class="sm-room sm-room--${room.signal}" tabindex="0" role="button"></div>`
		);
		// Base geometry + the signal colour key (danger/warning/clear) overlaid.
		$tile.attr("style", SM_STYLE.tile_base + (SM_SIGNAL[room.signal] || ""));

		// [#r0gsu1] An open red/amber signal gets a static ring (no keyframe pulse —
		// Desk pages ship no stylesheet for @keyframes) to draw the eye.
		if (room.signal === "red" || room.signal === "amber") {
			$tile.css("box-shadow", "0 0 0 2px " + (room.signal === "red" ? "var(--red-500)" : "var(--orange-500)"));
		}

		$('<div class="sm-room-number"></div>')
			.attr("style", SM_STYLE.room_number)
			.text(`${__("Room")} ${room.room_number || room.room}`)
			.appendTo($tile);

		if (room.has_open_maintenance) {
			$('<div class="sm-room-badge"></div>')
				.attr("style", SM_STYLE.badge)
				.text(`${__("Open Maintenance")} · ${room.maintenance_count}`)
				.appendTo($tile);
		} else {
			$('<div class="sm-room-badge sm-room-badge--ok"></div>')
				.attr("style", SM_STYLE.badge + "opacity:0.75;")
				.text(__("Clear"))
				.appendTo($tile);
		}

		const handler = () => this._open_inspection_dialog(floor, null);
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
		const $tile = $('<div class="sm-zone" tabindex="0" role="button"></div>').attr("style", SM_STYLE.zone);
		$('<div class="sm-zone-icon"></div>').css("font-size", "18px").text("◇").appendTo($tile);
		$('<div class="sm-zone-label"></div>').css("font-size", "var(--text-sm, 12px)").text(zone.zone_label).appendTo($tile);

		const handler = () => this._open_inspection_dialog(floor, zone.zone_label);
		$tile.on("click", handler);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
		return $tile;
	}

	_open_inspection_dialog(floor, zone_label) {
		const floor_val = floor && floor.floor ? floor.floor : null;
		const scope_label = zone_label
			? zone_label
			: floor
			? floor.floor_label
			: this.data.building_title || this.building;

		const d = new frappe.ui.Dialog({
			title: __("Log Inspection — {0}", [scope_label]),
			fields: [
				{
					fieldname: "scope_info",
					fieldtype: "HTML",
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(
						`${this.data.building_title || this.building} · ${scope_label}`
					)}</div>`,
				},
				{
					fieldname: "overall_result",
					label: __("Overall Result"),
					fieldtype: "Select",
					options: "Pass\nNeeds Attention\nFail",
					default: "Pass",
				},
				{
					fieldname: "notes",
					label: __("Finding Description"),
					fieldtype: "Small Text",
				},
			],
			primary_action_label: __("Log Inspection"),
			primary_action: (values) => {
				frappe.call({
					method: "apex_habitat.habitat.api.safety_map.log_building_inspection",
					args: {
						building: this.building,
						floor: floor_val,
						zone_label: zone_label || null,
						overall_result: values.overall_result || null,
						notes: values.notes || null,
					},
					freeze: true,
					freeze_message: __("Logging inspection…"),
					callback: (r) => {
						if (r.exc || !r.message) {
							frappe.show_alert({
								message: __("Could not log the inspection. Please try again."),
								indicator: "red",
							});
							return;
						}
						d.hide();
						frappe.show_alert({
							message: __("Inspection logged: {0}", [r.message.report]),
							indicator: "green",
						});
						// [#1q9tno]
						this.refresh();
					},
					error: () => {
						frappe.show_alert({
							message: __("Could not log the inspection. Please try again."),
							indicator: "red",
						});
					},
				});
			},
		});
		d.show();
	}
}
