// Room Setup — a staged, mobile-friendly wizard to define floors, room types and
// bed counts for an Accommodation Building, then create the Room + Bed records via
// the safe server generator (setup_building_rooms -> generate_rooms_and_beds).
// Native Frappe page (make_app_page), normal DOM only — no shadow DOM, no presets.

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

class RoomSetup {
	constructor(page) {
		this.page = page;
		this.building = (frappe.get_route() || [])[1] || null;
		this.stage = 1;
		this.floors = []; // [{number, type, rooms_per_floor, def_type, def_beds, rooms:[{type,beds}]}]
		this.$body = $('<div class="room-setup"></div>').appendTo(this.page.main);
		this._inject_styles();

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
		const $h = $('<div class="rs-steps"></div>').appendTo(this.$body);
		labels.forEach((l, i) => {
			const n = i + 1;
			const cls = n === this.stage ? "active" : n < this.stage ? "done" : "";
			$(`<div class="rs-step ${cls}"></div>`)
				.html(`<span class="rs-step-no">${n}</span> ${frappe.utils.escape_html(l)}`)
				.appendTo($h);
		});
	}

	// ----- Stage 1: floor definition -----
	_stage_floors() {
		const $wrap = $('<div class="rs-stage"></div>').appendTo(this.$body);
		$('<p class="text-muted"></p>')
			.text(__("Define the floors: rooms per floor, floor type, and the default room type and bed count."))
			.appendTo($wrap);

		const $tbl = $('<div class="rs-floors"></div>').appendTo($wrap);
		const $head = $('<div class="rs-frow rs-fhead"></div>').appendTo($tbl);
		[__("#"), __("Floor Type"), __("Rooms"), __("Default Room Type"), __("Default Beds"), ""].forEach((h) =>
			$('<div class="rs-fcell"></div>').text(h).appendTo($head)
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
		const $r = $('<div class="rs-frow"></div>').appendTo($tbl);
		$('<div class="rs-fcell rs-fno"></div>').text(f.number).appendTo($r);

		const $type = $('<select class="form-control input-sm"></select>').appendTo(
			$('<div class="rs-fcell"></div>').appendTo($r)
		);
		RS_FLOOR_TYPES.forEach((t) => $("<option></option>").val(t).text(__(t)).appendTo($type));
		$type.val(f.type).on("change", () => (f.type = $type.val()));

		const $rooms = $('<input type="number" min="1" class="form-control input-sm">')
			.val(f.rooms_per_floor)
			.appendTo($('<div class="rs-fcell"></div>').appendTo($r));
		$rooms.on("change", () => (f.rooms_per_floor = cint($rooms.val()) || 1));

		const $dtype = $('<select class="form-control input-sm"></select>').appendTo(
			$('<div class="rs-fcell"></div>').appendTo($r)
		);
		RS_ROOM_TYPES.forEach((t) => $("<option></option>").val(t).text(__(t)).appendTo($dtype));
		$dtype.val(f.def_type).on("change", () => (f.def_type = $dtype.val()));

		const $beds = $('<input type="number" min="0" class="form-control input-sm">')
			.val(f.def_beds)
			.appendTo($('<div class="rs-fcell"></div>').appendTo($r));
		$beds.on("change", () => (f.def_beds = cint($beds.val())));

		const $del = $('<div class="rs-fcell"></div>').appendTo($r);
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
		// (Re)build each floor's rooms[] from counts/defaults, keeping prior overrides
		// where the position still exists.
		this.floors.forEach((f) => {
			const n = Math.max(1, cint(f.rooms_per_floor) || 1);
			const old = f.rooms || [];
			f.rooms = [];
			for (let i = 0; i < n; i++) {
				f.rooms.push(old[i] ? old[i] : { type: f.def_type, beds: cint(f.def_beds) });
			}
		});
	}

	// ----- Stage 2: per-room type -----
	_stage_types() {
		const $wrap = $('<div class="rs-stage"></div>').appendTo(this.$body);
		$('<p class="text-muted"></p>')
			.text(__("Walk each floor and set the type of every room."))
			.appendTo($wrap);
		this.floors.forEach((f) =>
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

	// ----- Stage 3: per-room beds -----
	_stage_beds() {
		const $wrap = $('<div class="rs-stage"></div>').appendTo(this.$body);
		$('<p class="text-muted"></p>')
			.text(__("Set the number of beds in each room. Use − / + to adjust."))
			.appendTo($wrap);
		this.floors.forEach((f) =>
			this._floor_block($wrap, f, (rm) => {
				const $st = $('<div class="rs-stepper"></div>');
				const $val = $('<span class="rs-bed-val"></span>').text(rm.beds);
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
		const $b = $('<div class="rs-floor-block"></div>').appendTo($wrap);
		$('<div class="rs-floor-title"></div>')
			.text(__("Floor {0} — {1}", [f.number, __(f.type || "")]))
			.appendTo($b);
		const $grid = $('<div class="rs-grid"></div>').appendTo($b);
		(f.rooms || []).forEach((rm, i) => {
			const $card = $('<div class="rs-room"></div>').appendTo($grid);
			$('<div class="rs-room-no"></div>').text("#" + (i + 1)).appendTo($card);
			cellFn(rm).appendTo($card);
		});
	}

	// ----- Stage 4: review + approve -----
	_stage_review() {
		const $wrap = $('<div class="rs-stage"></div>').appendTo(this.$body);
		let rooms = 0, beds = 0;
		this.floors.forEach((f) => (f.rooms || []).forEach((rm) => { rooms += 1; beds += cint(rm.beds); }));

		const $sum = $('<div class="rs-summary"></div>').appendTo($wrap);
		const card = (n, l) => $('<div class="rs-sum-card"></div>').html(`<div class="rs-sum-n">${n}</div><div class="rs-sum-l">${frappe.utils.escape_html(l)}</div>`).appendTo($sum);
		card(this.floors.length, __("Floors"));
		card(rooms, __("Rooms"));
		card(beds, __("Beds"));

		const $list = $('<div class="rs-review"></div>').appendTo($wrap);
		this._grouped_floor_plan().forEach((row) => {
			$('<div class="rs-review-row"></div>')
				.text(__("Floor {0} ({1}): {2} room(s) × {3}, {4} bed(s) each", [row.floor_number, __(row.floor_type || "-"), row.room_count, __(row.room_type), row.bed_capacity_per_room]))
				.appendTo($list);
		});

		$('<p class="text-muted rs-note"></p>')
			.text(__("Approving creates the rooms and beds and saves the floor plan on the building."))
			.appendTo($wrap);

		this._footer(
			() => { this.stage = 3; this.render(); },
			__("Approve & Generate"),
			() => this._approve(),
			"btn-primary"
		);
	}

	_grouped_floor_plan() {
		const rows = [];
		this.floors.forEach((f) => {
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
					floor_number: f.number,
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
			frappe.msgprint(__("Add at least one floor with rooms."));
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
		const $f = $('<div class="rs-footer"></div>').appendTo(this.$body);
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
		$('<div class="rs-fatal text-muted"></div>').text(msg).appendTo(this.$body);
	}

	_inject_styles() {
		if (document.getElementById("rs-styles")) return;
		const css = `
.room-setup{max-width:900px;margin:0 auto;padding:8px 0 70px}
.rs-steps{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.rs-step{flex:1;min-width:84px;padding:6px 8px;border-radius:6px;background:var(--control-bg,#f4f5f6);color:var(--text-muted);font-size:12px;text-align:center}
.rs-step.active{background:var(--primary,#2490ef);color:#fff}
.rs-step.done{background:var(--green-100,#e3f6e3);color:var(--green-700,#1f7a1f)}
.rs-step-no{display:inline-block;width:18px;height:18px;line-height:18px;border-radius:50%;background:rgba(0,0,0,.12);text-align:center;margin-right:3px;font-weight:600}
.rs-stage{margin-bottom:12px}
.rs-floors{display:flex;flex-direction:column;gap:6px;margin:10px 0}
.rs-frow{display:grid;grid-template-columns:34px 1.3fr .8fr 1.3fr .8fr 40px;gap:8px;align-items:center}
.rs-fhead .rs-fcell{font-size:11px;color:var(--text-muted);text-transform:uppercase}
.rs-fno{font-weight:600;color:var(--text-muted)}
.rs-floor-block{margin:14px 0;padding:12px;border:1px solid var(--border-color,#e8e8e8);border-radius:8px}
.rs-floor-title{font-weight:600;margin-bottom:10px}
.rs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
.rs-room{border:1px solid var(--border-color,#e8e8e8);border-radius:8px;padding:8px;background:var(--card-bg,#fff)}
.rs-room-no{font-size:11px;color:var(--text-muted);margin-bottom:4px}
.rs-stepper{display:flex;align-items:center;gap:8px;justify-content:space-between}
.rs-stepper .btn{width:36px;height:36px;font-size:18px;padding:0;line-height:1}
.rs-bed-val{font-weight:600;font-size:16px}
.rs-summary{display:flex;gap:10px;margin:10px 0}
.rs-sum-card{flex:1;text-align:center;padding:14px;border-radius:8px;background:var(--control-bg,#f4f5f6)}
.rs-sum-n{font-size:26px;font-weight:700}
.rs-sum-l{font-size:12px;color:var(--text-muted)}
.rs-review-row{padding:6px 0;border-bottom:1px solid var(--border-color,#eee);font-size:13px}
.rs-note{margin-top:12px}
.rs-footer{display:flex;justify-content:space-between;gap:10px;margin-top:18px;position:sticky;bottom:0;background:var(--fg-color,#fff);padding:10px 0}
.rs-footer .btn{min-width:120px}
.rs-add{margin-top:6px}
@media(max-width:600px){.rs-frow{grid-template-columns:26px 1fr 1fr 40px}.rs-fhead{display:none}.rs-frow .rs-fcell:nth-child(4){grid-column:2}.rs-frow .rs-fcell:nth-child(5){grid-column:3}}
`;
		const style = document.createElement("style");
		style.id = "rs-styles";
		style.textContent = css;
		document.head.appendChild(style);
	}
}
