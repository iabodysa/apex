// Copyright (c) 2026, AFMCO and contributors
// [#gr1kmo]

frappe.pages["room-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Room Setup"),
		single_column: true,
	});
	wrapper.room_setup = new RoomSetup(page);
};

const RS_ROOM_TYPES = [
	"Worker", "Driver", "Supervisor", "Office", "Storage", "Isolation", "Maintenance", "Standard", "Other",
];
const RS_FLOOR_TYPES = ["Ground", "Middle", "Roof", "Basement"];

// Desk pages ship no stylesheet — wizard layout is inline styles bound to native
// Desk CSS variables (theme/dark-mode aware).
const RS_STYLE = {
	steps: "display:flex;flex-wrap:wrap;gap:8px;margin-block:var(--margin-sm,10px) var(--margin-lg,20px);",
	step:
		"display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border:1px solid var(--border-color);border-radius:16px;font-size:var(--text-sm,12px);color:var(--text-muted);background:var(--card-bg);",
	step_active: "border-color:var(--primary);color:var(--text-on-blue,#fff);background:var(--primary);font-weight:600;",
	step_done: "border-color:var(--green-500);color:var(--green-700);background:var(--green-100);",
	step_no:
		"display:inline-flex;align-items:center;justify-content:center;inline-size:18px;block-size:18px;border-radius:50%;background:var(--control-bg);color:var(--text-color);font-size:11px;font-weight:700;",
	stage: "display:flex;flex-direction:column;gap:var(--margin-sm,10px);",
	floors: "border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);overflow:hidden;",
	frow:
		"display:grid;grid-template-columns:48px 1.4fr 0.8fr 1.4fr 0.8fr 48px;gap:8px;align-items:center;padding:8px var(--padding-sm,10px);border-block-end:1px solid var(--border-color);",
	fhead: "background:var(--subtle-fg,var(--control-bg));font-weight:600;font-size:var(--text-sm,12px);color:var(--text-muted);",
	fcell: "min-inline-size:0;",
	fno: "font-weight:600;",
	floor_block:
		"border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:var(--padding-md,15px);background:var(--card-bg);",
	floor_title: "font-weight:600;font-size:var(--text-md,14px);margin-block-end:var(--margin-sm,10px);",
	grid: "display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:var(--margin-sm,10px);",
	room:
		"border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:var(--padding-sm,10px);background:var(--fg-color,var(--card-bg));display:flex;flex-direction:column;gap:6px;",
	room_no: "font-weight:600;font-size:var(--text-sm,12px);color:var(--text-muted);",
	stepper: "display:inline-flex;align-items:center;gap:8px;",
	bed_val: "min-inline-size:24px;text-align:center;font-weight:700;",
	summary: "display:flex;gap:var(--margin-md,15px);flex-wrap:wrap;",
	sum_card:
		"border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:var(--padding-md,15px);background:var(--card-bg);text-align:center;min-inline-size:96px;",
	sum_n: "font-size:24px;font-weight:700;",
	sum_l: "font-size:var(--text-sm,12px);color:var(--text-muted);",
	review:
		"display:flex;flex-direction:column;gap:6px;border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:var(--padding-md,15px);background:var(--card-bg);",
	review_row: "font-size:var(--text-sm,12px);padding-block:2px;border-block-end:1px solid var(--border-color);",
	footer:
		"display:flex;justify-content:space-between;gap:8px;margin-block-start:var(--margin-lg,20px);padding-block-start:var(--padding-md,15px);border-block-start:1px solid var(--border-color);",
	fatal: "padding-block:var(--padding-xl,30px);text-align:center;",
};

class RoomSetup {
	constructor(page) {
		this.page = page;
		this.building = (frappe.get_route() || [])[1] || null;
		this.stage = 1;
		this.floors = []; // [{number, type, rooms_per_floor, def_type, def_beds, rooms:[{type,beds}]}]
		this.$body = $('<div class="room-setup"></div>').appendTo(this.page.main);

		if (!this.building) {
			this._fatal(__("Open Room Setup from a building — no building was provided in the route."));
			return;
		}
		frappe.db
			.get_value("Accommodation Building", this.building, "building_name")
			.then((r) => {
				this.buildingName = (r && r.message && r.message.building_name) || this.building;
				this.page.set_title(__("Room Setup — {0}", [this.buildingName]));
				if (!this.floors.length) this._seed_one_floor();
				this.render();
			})
			.catch(() => this._fatal(__("Could not load the building.")));
	}

	_seed_one_floor() {
		this.floors = [
			{ number: 1, type: "Ground", rooms_per_floor: 10, def_type: "Worker", def_beds: 6, rooms: [] },
		];
	}

	render() {
		this.$body.empty();
		this._steps_header();
		if (this.stage === 1) this._stage_floors();
		else if (this.stage === 2) this._stage_types();
		else if (this.stage === 3) this._stage_beds();
		else this._stage_review();
	}

	_steps_header() {
		const labels = [__("Floors"), __("Room Types"), __("Beds"), __("Approve")];
		const $h = $('<div class="rs-steps"></div>').attr("style", RS_STYLE.steps).appendTo(this.$body);
		labels.forEach((l, i) => {
			const n = i + 1;
			const cls = n === this.stage ? "active" : n < this.stage ? "done" : "";
			const tone = n === this.stage ? RS_STYLE.step_active : n < this.stage ? RS_STYLE.step_done : "";
			$(`<div class="rs-step ${cls}"></div>`)
				.attr("style", RS_STYLE.step + tone)
				.html(`<span class="rs-step-no" style="${RS_STYLE.step_no}">${n}</span> ${frappe.utils.escape_html(l)}`)
				.appendTo($h);
		});
	}

	// [#aw8tj4]
	_stage_floors() {
		const $wrap = $('<div class="rs-stage"></div>').attr("style", RS_STYLE.stage).appendTo(this.$body);
		$('<p class="text-muted"></p>')
			.text(__("Define the floors: rooms per floor, floor type, and the default room type and bed count."))
			.appendTo($wrap);

		const $tbl = $('<div class="rs-floors"></div>').attr("style", RS_STYLE.floors).appendTo($wrap);
		const $head = $('<div class="rs-frow rs-fhead"></div>').attr("style", RS_STYLE.frow + RS_STYLE.fhead).appendTo($tbl);
		[__("#"), __("Floor Type"), __("Rooms"), __("Default Room Type"), __("Default Beds"), ""].forEach((h) =>
			$('<div class="rs-fcell"></div>').attr("style", RS_STYLE.fcell).text(h).appendTo($head)
		);
		this.floors.forEach((f, idx) => this._floor_row($tbl, f, idx));

		$('<button class="btn btn-sm btn-default rs-add"></button>')
			.html(frappe.utils.icon("add", "sm") + " " + __("Add Floor"))
			.on("click", () => {
				const last = this.floors[this.floors.length - 1];
				this.floors.push({
					number: (last ? last.number : 0) + 1,
					type: "Middle",
					rooms_per_floor: last ? last.rooms_per_floor : 10,
					def_type: last ? last.def_type : "Worker",
					def_beds: last ? last.def_beds : 6,
					rooms: [],
				});
				this.render();
			})
			.appendTo($wrap);

		this._footer(null, __("Next: Room Types"), () => {
			this._materialize_rooms();
			this.stage = 2;
			this.render();
		});
	}

	_floor_row($tbl, f, idx) {
		const $r = $('<div class="rs-frow"></div>').attr("style", RS_STYLE.frow).appendTo($tbl);
		$('<div class="rs-fcell rs-fno"></div>').attr("style", RS_STYLE.fcell + RS_STYLE.fno).text(f.number).appendTo($r);

		const $type = $('<select class="form-control input-sm"></select>').appendTo(
			$('<div class="rs-fcell"></div>').attr("style", RS_STYLE.fcell).appendTo($r)
		);
		RS_FLOOR_TYPES.forEach((t) => $("<option></option>").val(t).text(__(t)).appendTo($type));
		$type.val(f.type).on("change", () => (f.type = $type.val()));

		const $rooms = $('<input type="number" min="1" class="form-control input-sm">')
			.val(f.rooms_per_floor)
			.appendTo($('<div class="rs-fcell"></div>').attr("style", RS_STYLE.fcell).appendTo($r));
		$rooms.on("change", () => (f.rooms_per_floor = cint($rooms.val()) || 1));

		const $dtype = $('<select class="form-control input-sm"></select>').appendTo(
			$('<div class="rs-fcell"></div>').attr("style", RS_STYLE.fcell).appendTo($r)
		);
		RS_ROOM_TYPES.forEach((t) => $("<option></option>").val(t).text(__(t)).appendTo($dtype));
		$dtype.val(f.def_type).on("change", () => (f.def_type = $dtype.val()));

		const $beds = $('<input type="number" min="0" class="form-control input-sm">')
			.val(f.def_beds)
			.appendTo($('<div class="rs-fcell"></div>').attr("style", RS_STYLE.fcell).appendTo($r));
		$beds.on("change", () => (f.def_beds = cint($beds.val())));

		const $del = $('<div class="rs-fcell"></div>').attr("style", RS_STYLE.fcell).appendTo($r);
		if (this.floors.length > 1) {
			$('<button class="btn btn-xs btn-default"></button>')
				.html(frappe.utils.icon("delete", "sm"))
				.on("click", () => {
					this.floors.splice(idx, 1);
					this.render();
				})
				.appendTo($del);
		}
	}

	_materialize_rooms() {
		// [#mm9vce]
		this.floors.forEach((f) => {
			const n = Math.max(1, cint(f.rooms_per_floor) || 1);
			const old = f.rooms || [];
			f.rooms = [];
			for (let i = 0; i < n; i++) {
				f.rooms.push(old[i] ? old[i] : { type: f.def_type, beds: cint(f.def_beds) });
			}
		});
	}

	// [#pax34c]
	_stage_types() {
		const $wrap = $('<div class="rs-stage"></div>').attr("style", RS_STYLE.stage).appendTo(this.$body);
		$('<p class="text-muted"></p>')
			.text(__("Walk each floor and set the type of every room."))
			.appendTo($wrap);
		this._orderedFloors().forEach((f) =>
			this._floor_block($wrap, f, (rm) => {
				const $sel = $('<select class="form-control input-sm"></select>');
				RS_ROOM_TYPES.forEach((t) => $("<option></option>").val(t).text(__(t)).appendTo($sel));
				$sel.val(rm.type).on("change", () => (rm.type = $sel.val()));
				return $sel;
			})
		);
		this._footer(
			() => { this.stage = 1; this.render(); },
			__("Next: Beds"),
			() => { this.stage = 3; this.render(); }
		);
	}

	// [#gnqe4p]
	_stage_beds() {
		const $wrap = $('<div class="rs-stage"></div>').attr("style", RS_STYLE.stage).appendTo(this.$body);
		$('<p class="text-muted"></p>')
			.text(__("Set the number of beds in each room. Use − / + to adjust."))
			.appendTo($wrap);
		this._orderedFloors().forEach((f) =>
			this._floor_block($wrap, f, (rm) => {
				const $st = $('<div class="rs-stepper"></div>').attr("style", RS_STYLE.stepper);
				const $val = $('<span class="rs-bed-val"></span>').attr("style", RS_STYLE.bed_val).text(rm.beds);
				$('<button class="btn btn-xs btn-default">−</button>')
					.on("click", () => { rm.beds = Math.max(0, cint(rm.beds) - 1); $val.text(rm.beds); })
					.appendTo($st);
				$val.appendTo($st);
				$('<button class="btn btn-xs btn-default">+</button>')
					.on("click", () => { rm.beds = cint(rm.beds) + 1; $val.text(rm.beds); })
					.appendTo($st);
				return $st;
			})
		);
		this._footer(
			() => { this.stage = 2; this.render(); },
			__("Next: Approve"),
			() => { this.stage = 4; this.render(); }
		);
	}

	_floor_block($wrap, f, cellFn) {
		const $b = $('<div class="rs-floor-block"></div>').attr("style", RS_STYLE.floor_block).appendTo($wrap);
		$('<div class="rs-floor-title"></div>')
			.attr("style", RS_STYLE.floor_title)
			.text(__("Floor {0} — {1}", [f._code || f.number, __(f.type || "")]))
			.appendTo($b);
		const $grid = $('<div class="rs-grid"></div>').attr("style", RS_STYLE.grid).appendTo($b);
		(f.rooms || []).forEach((rm, i) => {
			const $card = $('<div class="rs-room"></div>').attr("style", RS_STYLE.room).appendTo($grid);
			$('<div class="rs-room-no"></div>').attr("style", RS_STYLE.room_no).text("#" + (i + 1)).appendTo($card);
			cellFn(rm).appendTo($card);
		});
	}

	// [#13u2dc]
	_stage_review() {
		const $wrap = $('<div class="rs-stage"></div>').attr("style", RS_STYLE.stage).appendTo(this.$body);
		let rooms = 0, beds = 0;
		this.floors.forEach((f) => (f.rooms || []).forEach((rm) => { rooms += 1; beds += cint(rm.beds); }));

		const $sum = $('<div class="rs-summary"></div>').attr("style", RS_STYLE.summary).appendTo($wrap);
		const card = (n, l) => $('<div class="rs-sum-card"></div>').attr("style", RS_STYLE.sum_card).html(`<div class="rs-sum-n" style="${RS_STYLE.sum_n}">${n}</div><div class="rs-sum-l" style="${RS_STYLE.sum_l}">${frappe.utils.escape_html(l)}</div>`).appendTo($sum);
		card(this.floors.length, __("Floors"));
		card(rooms, __("Rooms"));
		card(beds, __("Beds"));

		const $list = $('<div class="rs-review"></div>').attr("style", RS_STYLE.review).appendTo($wrap);
		this._grouped_floor_plan().forEach((row) => {
			$('<div class="rs-review-row"></div>')
				.attr("style", RS_STYLE.review_row)
				.text(__("Floor {0} ({1}): {2} room(s) × {3}, {4} bed(s) each", [row.floor_number, __(row.floor_type || "-"), row.room_count, __(row.room_type), row.bed_capacity_per_room]))
				.appendTo($list);
		});

		$('<p class="text-muted rs-note"></p>')
			.text(__("Approving creates the rooms and beds and saves the floor plan on the building."))
			.appendTo($wrap);

		this._footer(
			() => { this.stage = 3; this.render(); },
			__("Approve and Generate"),
			() => this._approve(),
			"btn-primary"
		);
	}

	_orderedFloors() {
		// [#7me1f7]
		const PRI = { Basement: 0, Ground: 1, Middle: 2, Roof: 3 };
		const pri = (t) => (t in PRI ? PRI[t] : 2);
		const sorted = this.floors.slice().sort(
			(a, z) => pri(a.type) - pri(z.type) || this.floors.indexOf(a) - this.floors.indexOf(z)
		);
		let b = 0, m = 0, r = 0;
		return sorted.map((f) => {
			let num, code;
			if (f.type === "Basement") { num = ++b; code = "B" + num; }
			else if (f.type === "Ground") { num = 0; code = "G"; }
			else if (f.type === "Roof") { r++; num = r; code = r > 1 ? "R" + r : "R"; }
			else { num = ++m; code = String(num); }
			return Object.assign({}, f, { _num: num, _code: code });
		});
	}

	_grouped_floor_plan() {
		const rows = [];
		this._orderedFloors().forEach((f) => {
			const groups = {};
			const order = [];
			(f.rooms || []).forEach((rm) => {
				const key = rm.type + "||" + cint(rm.beds);
				if (!groups[key]) {
					groups[key] = { room_type: rm.type, bed_capacity_per_room: cint(rm.beds), count: 0 };
					order.push(key);
				}
				groups[key].count += 1;
			});
			let start = 1;
			order.forEach((key) => {
				const g = groups[key];
				rows.push({
					floor_number: f._num,
					floor_type: f.type || "",
					room_type: g.room_type,
					room_count: g.count,
					bed_capacity_per_room: g.bed_capacity_per_room,
					starting_room_number: start,
					generate_beds: g.bed_capacity_per_room > 0 ? 1 : 0,
				});
				start += g.count;
			});
		});
		return rows;
	}

	_approve() {
		const floors = this._grouped_floor_plan();
		if (!floors.length) {
			frappe.show_alert({ message: __("Add at least one floor with rooms."), indicator: "orange" });
			return;
		}
		frappe.dom.freeze(__("Creating rooms and beds…"));
		frappe
			.call({
				method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.setup_building_rooms",
				args: { building_name: this.building, floors: JSON.stringify(floors) },
			})
			.then(() => {
				frappe.dom.unfreeze();
				frappe.show_alert({ message: __("Rooms and beds created."), indicator: "green" });
				frappe.set_route("Form", "Accommodation Building", this.building);
			})
			.catch(() => frappe.dom.unfreeze());
	}

	_footer(backFn, nextLabel, nextFn, nextCls) {
		const $f = $('<div class="rs-footer"></div>').attr("style", RS_STYLE.footer).appendTo(this.$body);
		if (backFn) {
			$('<button class="btn btn-default"></button>').text(__("Back")).on("click", backFn).appendTo($f);
		} else {
			$('<button class="btn btn-default"></button>')
				.text(__("Open Building"))
				.on("click", () => frappe.set_route("Form", "Accommodation Building", this.building))
				.appendTo($f);
		}
		$(`<button class="btn ${nextCls || "btn-primary"}"></button>`).text(nextLabel).on("click", nextFn).appendTo($f);
	}

	_fatal(msg) {
		this.$body.empty();
		$('<div class="rs-fatal text-muted"></div>').attr("style", RS_STYLE.fatal).text(msg).appendTo(this.$body);
	}
}
