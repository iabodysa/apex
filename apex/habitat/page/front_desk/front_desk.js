// Copyright (c) 2026, AFMCO and contributors

frappe.pages["front-desk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Front Desk"),
		single_column: true,
	});

	const fd = new FrontDesk(page);
	fd.setup();
};

const LAST_BUILDING_KEY = "fd:last-building";

function fd_int(n) {
	return format_number(cint(n), null, 0);
}

function fd_fraction(used, total) {
	return `${fd_int(used)}/${fd_int(total)}`;
}

function fd_percent(pct) {
	return `${fd_int(pct)}%`;
}

function fd_indicator_color(bed_color) {
	return { green: "green", red: "red", amber: "orange", grey: "gray" }[bed_color] || "gray";
}

const FD_BED_PALETTE = {
	green: "background:var(--green-100);border-color:var(--green-500);color:var(--green-700);",
	red: "background:var(--red-100);border-color:var(--red-500);color:var(--red-700);",
	amber: "background:var(--yellow-100);border-color:var(--orange-500);color:var(--orange-700);cursor:not-allowed;",
	grey: "background:var(--gray-100);border-color:var(--gray-400);color:var(--gray-600);cursor:not-allowed;",
};
const FD_PRESSURE_BORDER = {
	green: "var(--green-500)",
	amber: "var(--orange-500)",
	red: "var(--red-500)",
};
const FD_STYLE = {
	board: "padding-block:8px 32px;padding-inline:4px;",
	empty: "padding-block:48px;padding-inline:16px;text-align:center;font-size:15px;",
	buildings: "padding-inline:4px;padding-block-start:8px;",
	buildings_row: "display:flex;flex-wrap:wrap;gap:8px;",
	chip:
		"display:inline-flex;align-items:baseline;gap:8px;padding:6px 12px;border-radius:16px;border:1px solid var(--border-color);background:var(--card-bg);cursor:pointer;font-size:var(--text-sm,13px);max-inline-size:280px;",
	chip_selected: "border-color:var(--primary);box-shadow:0 0 0 1px var(--primary);",
	chip_name: "font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	chip_counts: "font-weight:700;",
	error: "padding-block:48px;padding-inline:16px;text-align:center;",
	error_msg: "font-size:15px;margin-block-end:12px;",
	summary:
		"position:sticky;inset-block-start:0;z-index:2;display:flex;flex-direction:column;gap:8px;margin-block-end:16px;padding-block:10px;padding-inline:4px;background:var(--fg-color,var(--card-bg));border-block-end:1px solid var(--border-color);",
	summary_head: "display:flex;flex-wrap:wrap;align-items:baseline;gap:12px;",
	summary_title: "font-size:18px;font-weight:600;",
	summary_stats: "display:flex;gap:10px;flex-wrap:wrap;",
	summary_stat:
		"display:flex;align-items:baseline;gap:6px;padding:4px 10px;border-radius:8px;border-inline-start:4px solid var(--border-color);background:var(--control-bg);white-space:nowrap;",
	summary_stat_num: "font-size:16px;font-weight:700;",
	summary_stat_label: "font-size:12px;color:var(--text-muted);",
	summary_meter: "display:flex;align-items:center;gap:10px;",
	summary_meter_track:
		"position:relative;flex:1 1 auto;block-size:6px;border-radius:3px;background:var(--control-bg);overflow:hidden;",
	summary_meter_fill: "block-size:100%;background:var(--primary);",
	summary_meter_label: "font-size:13px;font-weight:700;",
	summary_meter_caption: "font-size:12px;color:var(--text-muted);white-space:nowrap;",
	legend: "display:flex;flex-wrap:wrap;align-items:center;gap:16px;margin-block-end:16px;",
	legend_key: "display:flex;flex-wrap:wrap;gap:12px;",
	legend_item: "display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted);",
	legend_filters: "display:flex;flex-wrap:wrap;gap:8px;",
	legend_filter:
		"font-size:12px;padding:4px 10px;border-radius:14px;border:1px solid var(--border-color);background:var(--card-bg);color:var(--text-color);cursor:pointer;",
	legend_filter_active: "border-color:var(--primary);background:var(--primary);color:var(--text-on-blue,#fff);font-weight:600;",
	floor: "margin-block-end:24px;",
	rooms: "display:flex;flex-wrap:wrap;gap:14px;",
	room:
		"border:1px solid var(--border-color);border-radius:8px;padding:12px;min-inline-size:240px;flex:1 1 260px;background:var(--card-bg);",
	room_header: "display:flex;justify-content:space-between;align-items:baseline;margin-block-end:10px;gap:8px;",
	room_number: "font-weight:600;font-size:var(--text-md,14px);",
	room_meta: "font-size:12px;color:var(--text-muted);",
	beds: "display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:10px;",
	bed:
		"border-radius:8px;padding:12px 10px;min-block-size:84px;display:flex;flex-direction:column;gap:4px;cursor:pointer;border:2px solid transparent;user-select:none;background:var(--card-bg);",
	bed_code: "font-weight:700;font-size:15px;",
	bed_badge: "font-size:11px;font-weight:600;",
	bed_occupant: "font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	summary_requests: "cursor:pointer;font-size:13px;padding:2px 8px;border-radius:10px;color:var(--text-muted);background:var(--control-bg);",
	summary_requests_open: "color:var(--text-on-blue,#fff);background:var(--primary);font-weight:600;",
};

class FrontDesk {
	constructor(page) {
		this.page = page;
		this.building = null;
		this.filters = {
			only_available: false,
			hide_out_of_service: false,
			only_needs_readiness: false,
		};
	}

	setup() {
		this.$strip = $('<div class="fd-buildings"></div>').attr("style", FD_STYLE.buildings).appendTo(this.page.main);
		this.$container = $('<div class="fd-board"></div>').attr("style", FD_STYLE.board).appendTo(this.page.main);
		this._render_empty(__("Select a building to load the board."));
		this._setup_controls();
		this._load_buildings();
	}

	_setup_controls() {
		this.page.set_primary_action(__("Refresh Board"), () => {
			if (this.building) {
				this.refresh();
			} else {
				frappe.show_alert({
					message: __("Select a building to load the board."),
					indicator: "orange",
				});
			}
		}, "refresh");
	}

	_load_buildings() {
		this.$strip.empty();
		const $loading = $('<div class="fd-buildings-loading text-muted"></div>')
			.text(__("Loading buildings…"))
			.appendTo(this.$strip);
		let permission_denied = false;
		frappe.call({
			method: "apex.habitat.api.front_desk.list_supervisor_buildings",
			error_handlers: {
				PermissionError: () => {
					permission_denied = true;
					$loading.remove();
					frappe.hide_msgprint();
					this._render_strip_permission_gap();
				},
			},
			callback: (r) => {
				$loading.remove();
				if (r.exc) {
					this._render_strip_error();
					return;
				}
				this.buildings = r.message || [];
				this._render_buildings();
			},
			error: () => {
				if (permission_denied) return;
				$loading.remove();
				this._render_strip_error();
			},
		});
	}

	_render_strip_error() {
		this.$strip.empty();
		const $err = $('<div class="fd-buildings-error"></div>')
			.css({ display: "flex", "align-items": "center", gap: "8px", "padding-block": "8px" })
			.appendTo(this.$strip);
		$('<span class="fd-buildings-error-msg"></span>')
			.text(__("Could not load your buildings. Check your connection and try again."))
			.appendTo($err);
		$('<button class="btn btn-default btn-xs"></button>')
			.text(__("Retry"))
			.on("click", () => this._load_buildings())
			.appendTo($err);
	}

	_render_strip_permission_gap() {
		this.$strip.empty();
		$('<div class="fd-buildings-empty text-muted"></div>')
			.text(__("You don't have any building assigned. Ask an administrator to grant you a building."))
			.appendTo(this.$strip);
	}

	_building_pressure(b) {
		if ((b.available || 0) <= 0) return "red";
		if ((b.occupancy_pct || 0) >= 85) return "amber";
		return "green";
	}

	_render_buildings() {
		this.$strip.empty();
		if (!this.buildings || !this.buildings.length) {
			this._render_buildings_empty();
			return;
		}
		const $row = $('<div class="fd-buildings-row"></div>').attr("style", FD_STYLE.buildings_row).appendTo(this.$strip);
		this.buildings.forEach((b) => {
			this._render_building_chip($row, b);
		});
		this._auto_select_building();
	}

	_auto_select_building() {
		if (this.building) return;
		const only = this.buildings.length === 1 || this.buildings.some((b) => b.auto);
		if (only) {
			const target = this.buildings.find((b) => b.auto) || this.buildings[0];
			this._select_building(target.building);
			return;
		}
		let last = null;
		try {
			last = localStorage.getItem(LAST_BUILDING_KEY);
		} catch (e) {
			last = null;
		}
		if (last && this.buildings.some((b) => b.building === last)) {
			this._select_building(last);
		}
	}

	_render_building_chip($row, b) {
		const pressure = this._building_pressure(b);
		const is_selected = b.building === this.building;
		const selected = is_selected ? " fd-building-chip--selected" : "";
		const $chip = $(
			`<button class="fd-building-chip fd-building-chip--${pressure}${selected}" type="button"></button>`
		).appendTo($row);
		$chip.attr(
			"style",
			FD_STYLE.chip +
				`border-inline-start:4px solid ${FD_PRESSURE_BORDER[pressure] || "var(--border-color)"};` +
				(is_selected ? FD_STYLE.chip_selected : "")
		);
		$chip.attr("aria-pressed", is_selected);
		$chip.attr("title", b.building_title || b.building);
		$('<span class="fd-building-chip-name"></span>')
			.attr("style", FD_STYLE.chip_name)
			.text(b.building_title || b.building)
			.appendTo($chip);
		$('<bdi class="fd-building-chip-counts" dir="ltr"></bdi>')
			.attr("style", FD_STYLE.chip_counts)
			.text(fd_fraction(b.available, b.total_beds))
			.appendTo($chip);
		$chip.on("click", () => this._select_building(b.building));
	}

	_render_buildings_empty() {
		this.$strip.empty();
		const $empty = $('<div class="fd-buildings-empty text-muted"></div>')
			.text(__("No buildings to show."))
			.appendTo(this.$strip);
		frappe.call({
			method: "apex.habitat.api.front_desk.get_buildings_scope_state",
			callback: (r) => {
				if (r.exc || !r.message) return;
				if (r.message.is_scoped && !r.message.active_buildings) {
					$empty.text(
						__("You don't have any building assigned. Ask an administrator to grant you a building.")
					);
				} else if (!r.message.active_buildings) {
					$empty.text(__("No active buildings exist yet."));
				}
			},
		});
	}

	_select_building(building) {
		if (!building || building === this.building) return;
		this.building = building;
		try {
			localStorage.setItem(LAST_BUILDING_KEY, building);
		} catch (e) {
		}
		this._render_buildings();
		this.refresh();
	}

	refresh() {
		if (!this.building) return;
		const requested = this.building;
		this._render_loading();
		let permission_denied = false;
		frappe.call({
			method: "apex.habitat.api.front_desk.get_building_grid",
			args: { building: this.building },
			error_handlers: {
				PermissionError: () => {
					permission_denied = true;
					if (requested !== this.building) return;
					frappe.hide_msgprint();
					this._render_error(
						__("You don't have permission to view this building."),
						{ retry: false }
					);
				},
			},
			callback: (r) => {
				if (requested !== this.building) return;
				if (r.exc || !r.message) {
					this._render_error(__("Could not load the board for this building."));
					return;
				}
				this._render_grid(r.message);
			},
			error: () => {
				if (requested !== this.building || permission_denied) return;
				this._render_error(
					__("Could not load the board. Check your connection and try again.")
				);
			},
		});
	}

	_render_empty(message) {
		this.$container.empty();
		$(`<div class="fd-empty text-muted"></div>`)
			.attr("style", FD_STYLE.empty)
			.text(message)
			.appendTo(this.$container);
	}

	_render_loading() {
		this.$container.empty();
		const $wrap = $('<div class="fd-loading" aria-busy="true"></div>').appendTo(this.$container);
		$('<div class="fd-loading-label text-muted"></div>')
			.css("margin-block-end", "12px")
			.text(__("Loading board…"))
			.appendTo($wrap);
		const $skeleton = $('<div class="fd-skeleton-rooms"></div>').attr("style", FD_STYLE.rooms).appendTo($wrap);
		for (let i = 0; i < 6; i++) {
			$('<div class="skeleton-block"></div>')
				.css({ "min-inline-size": "240px", flex: "1 1 260px", height: "120px", "border-radius": "8px", background: "var(--skeleton-bg)" })
				.appendTo($skeleton);
		}
	}

	_render_error(message, opts) {
		const allow_retry = !opts || opts.retry !== false;
		this.$container.empty();
		const $err = $('<div class="fd-error"></div>').attr("style", FD_STYLE.error).appendTo(this.$container);
		$('<div class="fd-error-msg"></div>').attr("style", FD_STYLE.error_msg).text(message).appendTo($err);
		if (allow_retry) {
			$('<button class="btn btn-default btn-sm"></button>')
				.text(__("Retry"))
				.on("click", () => this.refresh())
				.appendTo($err);
		}
	}

	_render_grid(data) {
		this.$container.empty();

		this._render_summary_bar(data);

		this._render_legend();

		if (!data.floors || !data.floors.length) {
			this._render_empty(__("No beds found for this building."));
			return;
		}

		const floor_head = frappe.utils.is_rtl()
			? "font-size:var(--text-md,14px);font-weight:600;color:var(--text-muted);margin-block-end:10px;"
			: "font-size:var(--text-md,14px);font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-muted);margin-block-end:10px;";
		const NOT_READY = ["Needs Cleaning", "Needs Repair", "Out of Service"];
		data.floors.forEach((floor) => {
			const $floor = $('<div class="fd-floor"></div>').attr("style", FD_STYLE.floor).appendTo(this.$container);
			$('<div class="fd-floor-header"></div>')
				.attr("style", floor_head)
				.text(floor.floor_label)
				.appendTo($floor);
			const $rooms = $('<div class="fd-rooms"></div>').attr("style", FD_STYLE.rooms).appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				const needs_readiness = NOT_READY.includes(room.readiness_status);
				const $room = $('<div class="fd-room"></div>')
					.attr("style", FD_STYLE.room)
					.attr("data-needs-readiness", needs_readiness ? "1" : "0")
					.appendTo($rooms);
				const $rh = $('<div class="fd-room-header"></div>').attr("style", FD_STYLE.room_header).appendTo($room);
				const $rn = $('<span class="fd-room-number"></span>').attr("style", FD_STYLE.room_number).appendTo($rh);
				$rn.append(document.createTextNode(`${__("Room")} `));
				$('<bdi dir="ltr"></bdi>').text(room.room_number || room.room).appendTo($rn);
				const $rm = $('<span class="fd-room-meta"></span>').attr("style", FD_STYLE.room_meta).appendTo($rh);
				const room_type = __(room.room_type || "");
				if (room_type) {
					$rm.append(document.createTextNode(`${room_type} · `));
				}
				$('<bdi dir="ltr"></bdi>')
					.text(fd_fraction(room.current_occupancy, room.bed_capacity))
					.appendTo($rm);

				if (needs_readiness) {
					$('<button class="btn btn-xs btn-default fd-room-ready"></button>')
						.text(__("Mark Ready"))
						.on("click", () => this._mark_room_ready(room.room))
						.appendTo($rh);
				}

				const $beds = $('<div class="fd-beds"></div>').attr("style", FD_STYLE.beds).appendTo($room);
				(room.beds || []).forEach((bed) => {
					this._render_bed_card(bed, room, data.building)
						.attr("data-color", bed.bed_color)
						.appendTo($beds);
				});
			});
		});

		this._apply_filters();
	}

	_render_summary_bar(data) {
		const s = data.summary || {};
		const total = cint(s.total_beds);
		const occupied = cint(s.occupied);
		const pct = total ? Math.round((occupied / total) * 100) : 0;

		const $bar = $('<div class="fd-summary" role="status" aria-live="polite"></div>')
			.attr("style", FD_STYLE.summary)
			.appendTo(this.$container);

		const $head = $('<div class="fd-summary-head"></div>').attr("style", FD_STYLE.summary_head).appendTo($bar);
		$('<span class="fd-summary-title"></span>')
			.attr("style", FD_STYLE.summary_title)
			.text(data.building_title || data.building)
			.appendTo($head);
		this._render_open_requests_badge($head, data.building);

		const $stats = $('<div class="fd-summary-stats"></div>').attr("style", FD_STYLE.summary_stats).appendTo($bar);
		const STAT_BORDER = { green: "var(--green-500)", red: "var(--red-500)", amber: "var(--orange-500)", grey: "var(--gray-400)" };
		const stat = (key, label, value, tone) => {
			const $stat = $(`<div class="fd-summary-stat fd-summary-stat--${tone}"></div>`)
				.attr("style", FD_STYLE.summary_stat + `border-inline-start-color:${STAT_BORDER[tone] || "var(--border-color)"};`)
				.appendTo($stats);
			$('<bdi class="fd-summary-stat-num" dir="ltr"></bdi>').attr("style", FD_STYLE.summary_stat_num).text(fd_int(value)).appendTo($stat);
			$('<span class="fd-summary-stat-label"></span>').attr("style", FD_STYLE.summary_stat_label).text(label).appendTo($stat);
			$stat.attr("data-stat", key);
		};
		stat("available", __("Available"), s.available, "green");
		stat("occupied", __("Occupied"), s.occupied, "red");
		stat("blocked", __("Room not ready"), s.blocked, "amber");
		stat("out_of_service", __("Out of service"), s.out_of_service, "grey");

		const $meter = $('<div class="fd-summary-meter"></div>').attr("style", FD_STYLE.summary_meter).appendTo($bar);
		const $track = $(
			`<div class="fd-summary-meter-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"></div>`
		).attr("style", FD_STYLE.summary_meter_track).appendTo($meter);
		$('<div class="fd-summary-meter-fill"></div>')
			.attr("style", FD_STYLE.summary_meter_fill)
			.css("inline-size", `${pct}%`)
			.appendTo($track);
		$('<bdi class="fd-summary-meter-label" dir="ltr"></bdi>')
			.attr("style", FD_STYLE.summary_meter_label)
			.text(fd_percent(pct))
			.appendTo($meter);
		$('<span class="fd-summary-meter-caption"></span>')
			.attr("style", FD_STYLE.summary_meter_caption)
			.text(__("{0} of {1} beds available", [fd_int(s.available), fd_int(s.total_beds)]))
			.appendTo($meter);
	}

	_render_legend() {
		const $legend = $('<div class="fd-legend"></div>').attr("style", FD_STYLE.legend).appendTo(this.$container);

		const swatches = [
			["green", __("Available")],
			["red", __("Occupied")],
			["amber", __("Room not ready")],
			["grey", __("Out of service")],
		];
		const $key = $('<div class="fd-legend-key"></div>').attr("style", FD_STYLE.legend_key).appendTo($legend);
		swatches.forEach(([color, label]) => {
			const $item = $('<span class="fd-legend-item"></span>').attr("style", FD_STYLE.legend_item).appendTo($key);
			$(`<span class="fd-legend-dot indicator ${fd_indicator_color(color)}"></span>`).appendTo(
				$item
			);
			$('<span class="fd-legend-label"></span>').text(label).appendTo($item);
		});

		const toggles = [
			["only_available", __("Show only available")],
			["hide_out_of_service", __("Hide out of service")],
			["only_needs_readiness", __("Rooms needing readiness")],
		];
		const $filters = $('<div class="fd-legend-filters"></div>').attr("style", FD_STYLE.legend_filters).appendTo($legend);
		const set_filter_style = ($btn, on) => $btn.attr("style", FD_STYLE.legend_filter + (on ? FD_STYLE.legend_filter_active : ""));
		toggles.forEach(([key, label]) => {
			const active = this.filters[key];
			const $btn = $('<button type="button" class="fd-legend-filter"></button>')
				.toggleClass("fd-legend-filter--active", active)
				.attr("aria-pressed", active ? "true" : "false")
				.text(label)
				.appendTo($filters);
			set_filter_style($btn, active);
			$btn.on("click", () => {
				this.filters[key] = !this.filters[key];
				$btn.toggleClass("fd-legend-filter--active", this.filters[key]);
				$btn.attr("aria-pressed", this.filters[key] ? "true" : "false");
				set_filter_style($btn, this.filters[key]);
				this._apply_filters();
			});
		});
	}

	_apply_filters() {
		const f = this.filters;
		this.$container.find(".fd-bed").each((_i, el) => {
			const $bed = $(el);
			const color = $bed.attr("data-color");
			let show = true;
			if (f.only_available && color !== "green") show = false;
			if (f.hide_out_of_service && color === "grey") show = false;
			$bed.toggleClass("d-none", !show);
		});
		this.$container.find(".fd-room").each((_i, el) => {
			const $room = $(el);
			const needs_readiness = $room.attr("data-needs-readiness") === "1";
			const has_visible_bed = $room.find(".fd-bed:not(.d-none)").length > 0;
			const readiness_ok = !f.only_needs_readiness || needs_readiness;
			$room.toggleClass("d-none", !(has_visible_bed && readiness_ok));
		});
		this.$container.find(".fd-floor").each((_i, el) => {
			const $floor = $(el);
			const has_visible_room = $floor.find(".fd-room:not(.d-none)").length > 0;
			$floor.toggleClass("d-none", !has_visible_room);
		});
	}

	_render_open_requests_badge($summary, building) {
		const requested = building;
		frappe.call({
			method: "apex.habitat.api.front_desk.building_open_requests",
			args: { building: building },
			callback: (r) => {
				if (requested !== this.building || r.exc || !r.message) return;
				const count = r.message.open_requests || 0;
				const statuses = r.message.statuses || [];
				const indicator = count > 0 ? "fd-summary-requests--open" : "";
				$(`<span class="fd-summary-requests ${indicator}" role="button" tabindex="0"></span>`)
					.attr("style", FD_STYLE.summary_requests + (count > 0 ? FD_STYLE.summary_requests_open : ""))
					.text(__("{0} open requests", [fd_int(count)]))
					.on("click keydown", (e) => {
						if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
						e.preventDefault();
						frappe.set_route("List", "Resident Request", {
							building: building,
							status: ["in", statuses],
						});
					})
					.appendTo($summary);
			},
			error: () => {},
		});
	}

	_render_bed_card(bed, room, building) {
		const $card = $(`<div class="fd-bed" tabindex="0" role="button"></div>`);
		$card.attr("style", FD_STYLE.bed + (FD_BED_PALETTE[bed.bed_color] || ""));
		$('<bdi class="fd-bed-code" dir="ltr"></bdi>').attr("style", FD_STYLE.bed_code).text(bed.bed_code || bed.bed).appendTo($card);

		let badge = "";
		if (bed.bed_color === "green") badge = __("Available");
		else if (bed.bed_color === "red") badge = __("Occupied");
		else if (bed.bed_color === "amber") badge = __("Room not ready");
		else badge = __("Out of Service");
		$(`<span class="fd-bed-badge indicator-pill ${fd_indicator_color(bed.bed_color)}"></span>`)
			.attr("style", FD_STYLE.bed_badge)
			.text(badge)
			.appendTo($card);

		if (bed.bed_color === "red" && bed.occupant) {
			$('<div class="fd-bed-occupant"></div>')
				.attr("style", FD_STYLE.bed_occupant)
				.text(bed.occupant.employee_name || bed.occupant.employee)
				.appendTo($card);
		}

		const handler = () => this._on_bed_click(bed, room, building, $card);
		$card.on("click", handler);
		$card.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
		return $card;
	}

	_set_bed_updating($card, busy) {
		if (!$card) return;
		$card.attr("aria-busy", busy ? "true" : null);
	}

	_mark_room_ready(room) {
		frappe.call({
			method: "apex.habitat.api.front_desk.set_room_readiness",
			args: { room: room, status: "Ready" },
			callback: (r) => {
				if (r.exc || !r.message) return;
				frappe.show_alert({ message: __("Room marked ready."), indicator: "green" });
				this.refresh();
			},
			error: () => frappe.show_alert({ message: __("Could not mark the room ready."), indicator: "red" }),
		});
	}

	_on_bed_click(bed, room, building, $card) {
		switch (bed.bed_color) {
			case "green":
				this._open_check_in_dialog(bed, room, building, $card);
				break;
			case "red":
				this._open_check_out_dialog(bed, room, building, $card);
				break;
			case "amber":
				frappe.show_alert({
					message: __("This bed is in a room that is not ready. Resolve room readiness before check-in."),
					indicator: "orange",
				});
				break;
			default:
				frappe.show_alert({
					message: __("This bed is out of service and cannot be assigned."),
					indicator: "red",
				});
		}
	}

	_open_check_in_dialog(bed, room, building, $card) {
		const context = `${building} · ${__("Room")} ${room.room_number || room.room} · ${bed.bed_code || bed.bed}`;
		const d = new frappe.ui.Dialog({
			title: __("Quick Check-in"),
			fields: [
				{
					fieldname: "context",
					fieldtype: "HTML",
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(context)}</div>`,
				},
				{
					fieldname: "scan",
					label: __("Scan Iqama / Worker Link"),
					fieldtype: "Data",
					description: __("Scan or type an Iqama number or personal link, then press Enter to identify the worker."),
					onchange: function () {
						const id = (this.get_value && this.get_value()) || "";
						if (!id.trim()) return;
						frappe.call({
							method: "apex.habitat.api.front_desk.resolve_worker",
							args: { identifier: id.trim() },
							callback: (r) => {
								const $status = d.fields_dict.scan_status.$wrapper;
								if (r.exc || !r.message) {
									$status.html(`<div class="text-muted">${__("Could not identify the worker.")}</div>`);
									return;
								}
								const m = r.message;
								if (!m.found) {
									$status.html(`<div class="text-muted">${frappe.utils.escape_html(m.message || __("No worker matched."))}</div>`);
									return;
								}
								if (m.employee) {
									d.set_value("employee", m.employee);
								}
								const warn = m.has_active_assignment
									? `<div class="text-danger" style="margin-top:4px">${__("This worker already holds an active bed.")}</div>`
									: "";
								const tw = m.party_type === "Temporary Worker" && !m.employee
									? `<div class="text-muted" style="margin-top:4px">${__("Temporary Worker — use the Arrivals Desk to house this worker.")}</div>`
									: "";
								$status.html(
									`<div style="margin-top:4px"><b>${frappe.utils.escape_html(m.employee_name || m.party)}</b></div>${warn}${tw}`
								);
							},
						});
					},
				},
				{ fieldname: "scan_status", fieldtype: "HTML" },
				{
					fieldname: "employee",
					label: __("Employee"),
					fieldtype: "Link",
					options: "Employee",
					reqd: 1,
					onchange: function () {
						const emp = this.get_value && this.get_value();
						const photo = d.fields_dict.employee_photo;
						if (!emp) {
							photo.$wrapper.html("");
							return;
						}
						frappe.call({
							method: "apex.habitat.api.front_desk.get_employee_card",
							args: { employee: emp },
							callback: (r) => {
								if (r.exc || !r.message) {
									photo.$wrapper.html(
										`<div class="text-muted">${__("Could not load employee photo.")}</div>`
									);
									return;
								}
								const img = r.message.image
									? `<img src="${frappe.utils.escape_html(r.message.image)}" style="width:84px;height:84px;object-fit:cover;border-radius:6px;border:1px solid var(--border-color)">`
									: `<div class="text-muted">${__("No photo on file")}</div>`;
								photo.$wrapper.html(
									`<div style="margin:6px 0">${img}<div><b>${frappe.utils.escape_html(r.message.employee_name || emp)}</b></div></div>`
								);
							},
						});
					},
				},
				{ fieldname: "employee_photo", fieldtype: "HTML" },
				{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", reqd: 1 },
				{
					fieldname: "check_in_date",
					label: __("Check-in Date"),
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" },
				{
					fieldname: "assignment_type",
					label: __("Assignment Type"),
					fieldtype: "Select",
					options: "New Assignment\nTransfer\nReturn from Leave",
					default: "New Assignment",
				},
				{
					fieldname: "room_condition_snapshot",
					label: __("Room Condition Snapshot"),
					fieldtype: "Attach Image",
				},
			],
			primary_action_label: __("Check In"),
			primary_action: (values) => {
				d.hide();
				this._set_bed_updating($card, true);
				frappe.call({
					method: "apex.habitat.api.front_desk.quick_check_in",
					args: {
						bed: bed.bed,
						employee: values.employee,
						project: values.project,
						check_in_date: values.check_in_date,
						cost_center: values.cost_center || null,
						assignment_type: values.assignment_type || "New Assignment",
						room_condition_snapshot: values.room_condition_snapshot || null,
					},
					callback: (r) => {
						if (r.exc || !r.message) {
							this._set_bed_updating($card, false);
							return;
						}
						frappe.show_alert({
							message: __("Checked in: {0}", [r.message.assignment]),
							indicator: "green",
						});
						this.refresh();
					},
					error: () => this._set_bed_updating($card, false),
				});
			},
		});
		d.show();
	}

	_open_check_out_dialog(bed, room, building, $card) {
		const occupant = bed.occupant || {};

		if (occupant.has_custody) {
			const d = new frappe.ui.Dialog({
				title: __("Quick Check-out"),
				fields: [
					{
						fieldname: "msg",
						fieldtype: "HTML",
						options: `<div>${__("This resident has custody items. Opening the full Checkout form to clear custody.")}</div>`,
					},
				],
				primary_action_label: __("Open Checkout Form"),
				primary_action: () => {
					d.hide();
					frappe.new_doc("Housing Checkout", { assignment: occupant.assignment });
				},
			});
			d.show();
			return;
		}

		const d = new frappe.ui.Dialog({
			title: __("Quick Check-out"),
			fields: [
				{
					fieldname: "context",
					fieldtype: "HTML",
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(occupant.employee_name || "")}</div>`,
				},
				{
					fieldname: "checkout_date",
					label: __("Check-out Date"),
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{
					fieldname: "checkout_reason",
					label: __("Check-out Reason"),
					fieldtype: "Select",
					reqd: 1,
					options: "\nFinal Exit\nInternal Transfer\nProject Transfer\nAbsconding\nEnd of Contract",
				},
				{
					fieldname: "room_condition_snapshot",
					label: __("Room Condition Snapshot"),
					fieldtype: "Attach Image",
				},
			],
			primary_action_label: __("Check Out"),
			primary_action: (values) => {
				d.hide();
				this._set_bed_updating($card, true);
				frappe.call({
					method: "apex.habitat.api.front_desk.quick_check_out",
					args: {
						bed: bed.bed,
						checkout_date: values.checkout_date,
						checkout_reason: values.checkout_reason,
						room_condition_snapshot: values.room_condition_snapshot || null,
					},
					callback: (r) => {
						if (r.exc || !r.message) {
							this._set_bed_updating($card, false);
							return;
						}
						if (r.message.requires_full_form) {
							this._set_bed_updating($card, false);
							frappe.show_alert({
								message: __("This resident has custody items. Opening the full Checkout form to clear custody."),
								indicator: "orange",
							});
							frappe.new_doc("Housing Checkout", { assignment: r.message.assignment });
							return;
						}
						frappe.show_alert({
							message: __("Checked out: {0}", [r.message.checkout]),
							indicator: "green",
						});
						this.refresh();
					},
					error: () => this._set_bed_updating($card, false),
				});
			},
		});
		d.show();
	}
}
