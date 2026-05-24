// Client-side script for Accommodation Building
function _toggleFloorFields(frm) {
	const isApartment = frm.doc.accommodation_type === "Apartment";
	frm.set_df_property("total_floors", "hidden", isApartment ? 1 : 0);
}

frappe.ui.form.on("Accommodation Building", {
	refresh(frm) {
		_toggleFloorFields(frm);

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
			frm.add_custom_button(__("Quick Room Setup"), function () {
				showStep1(frm);
			}, __("Setup"));

			frm.add_custom_button(__("Generate from Table"), function () {
				frappe.confirm(
					__("Are you sure you want to generate rooms and beds from the floor plan?"),
					function () {
						_generateRoomsAndBeds(frm, 0);
					}
				);
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

// ---------------------------------------------------------------------------
// Step 1 — Building Identity
// ---------------------------------------------------------------------------
function showStep1(frm, prefill) {
	const d1 = new frappe.ui.Dialog({
		title: __("Room Generator — Step 1 of 3: Building Code"),
		fields: [
			{
				fieldname: "abbreviation",
				fieldtype: "Data",
				label: __("Building Abbreviation"),
				reqd: 1,
				default: (prefill && prefill.abbreviation) || frm.doc.abbreviation || "",
				description: __("Used in room/bed codes, e.g. JED1-G01."),
			},
			{
				fieldname: "has_ground_floor",
				fieldtype: "Check",
				label: __("Has Ground Floor (Floor 0)"),
				default: (prefill && prefill.has_ground_floor !== undefined) ? prefill.has_ground_floor : 1,
				description: __("Ground floor uses G, e.g. JED1-G01."),
			},
			{
				fieldname: "num_upper_floors",
				fieldtype: "Int",
				label: __("Number of Upper Floors"),
				reqd: 1,
				default: (prefill && prefill.num_upper_floors) || 3,
				description: __("Upper floors numbered 1, 2, 3…"),
			},
		],
		primary_action_label: __("Next →"),
		primary_action(values) {
			if (!values.abbreviation || !values.abbreviation.trim()) {
				frappe.msgprint({ message: __("Building Abbreviation is required."), indicator: "red" });
				return;
			}
			d1.hide();
			showStep2(frm, values);
		},
	});
	d1.show();
}

// ---------------------------------------------------------------------------
// Step 2 — Dynamic Floor Plan Builder
// ---------------------------------------------------------------------------
function showStep2(frm, step1Values, prefill) {
	const abbr = step1Values.abbreviation.trim().toUpperCase();
	const hasGround = !!step1Values.has_ground_floor;
	const numUpper = parseInt(step1Values.num_upper_floors) || 0;

	const ROOM_TYPES = ["Standard", "Worker", "Driver", "Supervisor", "Office", "Storage", "Isolation", "Maintenance", "Other"];

	function floorOptions(selectedFloor) {
		let opts = "";
		if (hasGround) opts += `<option value="0" ${selectedFloor === 0 ? "selected" : ""}>${__("Ground (G)")}</option>`;
		for (let i = 1; i <= numUpper; i++) {
			opts += `<option value="${i}" ${selectedFloor === i ? "selected" : ""}>${__("Floor")} ${i}</option>`;
		}
		return opts;
	}

	function typeOptions(selectedType) {
		return ROOM_TYPES.map(t =>
			`<option value="${t}" ${t === selectedType ? "selected" : ""}>${__(t)}</option>`
		).join("");
	}

	function renderRow(row) {
		return `<tr>
			<td><select class="fp-floor form-control input-xs" style="min-width:90px">${floorOptions(row.floor)}</select></td>
			<td><select class="fp-type form-control input-xs" style="min-width:110px">${typeOptions(row.room_type)}</select></td>
			<td><input type="number" class="fp-rooms form-control input-xs" value="${row.room_count}" min="1" style="width:60px"></td>
			<td><input type="number" class="fp-beds form-control input-xs" value="${row.beds_per_room}" min="0" style="width:60px"></td>
			<td style="text-align:center;vertical-align:middle"><input type="checkbox" class="fp-gen-beds" ${row.generate_beds ? "checked" : ""}></td>
			<td><button class="fp-remove btn btn-xs btn-danger">✕</button></td>
		</tr>`;
	}

	// Build default rows if no prefill
	let initialRows = (prefill && prefill.rows && prefill.rows.length) ? prefill.rows : [];
	if (!initialRows.length) {
		if (hasGround) initialRows.push({ floor: 0, room_type: "Worker", room_count: 10, beds_per_room: 4, generate_beds: 1 });
		for (let i = 1; i <= numUpper; i++) {
			initialRows.push({ floor: i, room_type: "Worker", room_count: 10, beds_per_room: 4, generate_beds: 1 });
		}
	}

	const tableHtml = `
		<div>
			<table class="table table-bordered table-condensed fp-table" style="font-size:13px;margin-bottom:6px">
				<thead>
					<tr style="background:#f5f5f5">
						<th>${__("Floor")}</th>
						<th>${__("Room Type")}</th>
						<th>${__("Rooms")}</th>
						<th>${__("Beds/Room")}</th>
						<th>${__("Gen.Beds")}</th>
						<th></th>
					</tr>
				</thead>
				<tbody class="fp-tbody">
					${initialRows.map(renderRow).join("")}
				</tbody>
			</table>
			<button class="fp-add btn btn-xs btn-default">+ ${__("Add Row")}</button>
			<p class="text-muted" style="margin-top:6px;font-size:12px">
				${__("Set Beds/Room to 0 for non-sleeping rooms (office, storage).")}
			</p>
		</div>`;

	const d2 = new frappe.ui.Dialog({
		title: __("Room Generator — Step 2 of 3: Floor Plan"),
		fields: [{ fieldname: "fp_html", fieldtype: "HTML", options: tableHtml }],
		primary_action_label: __("Next →"),
		primary_action() {
			const rows = [];
			let valid = true;
			d2.$body.find(".fp-tbody tr").each(function () {
				const floor = parseInt($(this).find(".fp-floor").val()) || 0;
				const rtype = $(this).find(".fp-type").val();
				const rcount = parseInt($(this).find(".fp-rooms").val()) || 0;
				const beds = parseInt($(this).find(".fp-beds").val()) || 0;
				const genBeds = $(this).find(".fp-gen-beds").is(":checked") ? 1 : 0;
				if (rcount <= 0) {
					frappe.msgprint({ message: __("Each row must have at least 1 room."), indicator: "red" });
					valid = false;
					return false;
				}
				if (genBeds && beds <= 0) {
					frappe.msgprint({ message: __("Beds per Room must be > 0 when Auto-Generate Beds is enabled."), indicator: "red" });
					valid = false;
					return false;
				}
				rows.push({ floor, room_type: rtype, room_count: rcount, beds_per_room: beds, generate_beds: genBeds });
			});
			if (!valid) return;
			if (!rows.length) {
				frappe.msgprint({ message: __("Add at least one floor plan row."), indicator: "red" });
				return;
			}
			d2.hide();
			showStep3(frm, step1Values, { rows });
		},
		secondary_action_label: __("← Back"),
		secondary_action() { d2.hide(); showStep1(frm, step1Values); },
	});
	d2.show();

	d2.$body.on("click", ".fp-remove", function () { $(this).closest("tr").remove(); });
	d2.$body.on("click", ".fp-add", function () {
		const defaultFloor = hasGround ? 0 : 1;
		d2.$body.find(".fp-tbody").append(renderRow({ floor: defaultFloor, room_type: "Worker", room_count: 10, beds_per_room: 4, generate_beds: 1 }));
	});
	d2.$body.on("change", ".fp-gen-beds", function () {
		const row = $(this).closest("tr");
		const bedsInput = row.find(".fp-beds");
		if (!$(this).is(":checked")) {
			bedsInput.val(0);
		} else if (parseInt(bedsInput.val()) === 0) {
			bedsInput.val(4);
		}
	});
}

// ---------------------------------------------------------------------------
// Step 3 — Review & Generate (per-row preview)
// ---------------------------------------------------------------------------
function showStep3(frm, step1Values, step2Values) {
	const abbr = step1Values.abbreviation.trim().toUpperCase();
	// Escape for HTML rendering only — the raw abbr is used in the API payload below.
	const abbrHtml = frappe.utils.escape_html(abbr);
	const rows = step2Values.rows;

	// Calculate starting_room_number per floor (auto-sequential)
	const floorCounters = {};
	const enriched = rows.map(row => {
		const fl = row.floor;
		if (!floorCounters[fl]) floorCounters[fl] = 1;
		const start = floorCounters[fl];
		floorCounters[fl] += row.room_count;
		const fc = fl === 0 ? "G" : String(fl);
		// exampleHtml is safe for innerHTML; raw example (with unescaped abbr) is kept for payload.
		const exampleHtml = `${abbrHtml}-${fc}${String(start).padStart(2, "0")}`;
		const example = `${abbr}-${fc}${String(start).padStart(2, "0")}`;
		return { ...row, starting: start, floorCode: fc, example, exampleHtml };
	});

	const totalRooms = enriched.reduce((s, r) => s + r.room_count, 0);
	const totalBeds = enriched.reduce((s, r) => s + (r.generate_beds ? r.room_count * r.beds_per_room : 0), 0);
	const sleepingRooms = enriched.filter(r => r.generate_beds && r.beds_per_room > 0).reduce((s, r) => s + r.room_count, 0);
	const nonSleeping = totalRooms - sleepingRooms;

	const tableRows = enriched.map(r => `
		<tr>
			<td>${r.floor === 0 ? __("Ground (G)") : __("Floor") + " " + r.floor}</td>
			<td>${__(r.room_type)}</td>
			<td>${r.room_count}</td>
			<td>${r.beds_per_room > 0 ? r.beds_per_room : "—"}</td>
			<td>${r.generate_beds ? r.room_count * r.beds_per_room : 0}</td>
			<td><code>${r.exampleHtml}</code></td>
		</tr>`).join("");

	const previewHtml = `
		<div style="margin-bottom:12px">
			<table class="table table-bordered table-condensed" style="font-size:13px">
				<thead>
					<tr style="background:#f5f5f5">
						<th>${__("Floor")}</th>
						<th>${__("Room Type")}</th>
						<th>${__("Rooms")}</th>
						<th>${__("Beds/Room")}</th>
						<th>${__("Total Beds")}</th>
						<th>${__("Example")}</th>
					</tr>
				</thead>
				<tbody>${tableRows}</tbody>
			</table>
			<p style="font-weight:600;margin-top:8px">
				${__("Total")}: ${totalRooms} ${__("rooms")}, ${totalBeds} ${__("beds")}<br>
				${__("Sleeping rooms")}: ${sleepingRooms} &nbsp;|&nbsp; ${__("Non-sleeping")}: ${nonSleeping}
			</p>
		</div>`;

	const d3 = new frappe.ui.Dialog({
		title: __("Room Generator — Step 3 of 3: Review"),
		fields: [{ fieldname: "preview", fieldtype: "HTML", options: previewHtml }],
		primary_action_label: __("Generate Rooms & Beds ✓"),
		primary_action() {
			d3.hide();
			_applyWizard(frm, {
				abbreviation: step1Values.abbreviation.trim(),
				rows: enriched.map(r => ({
					floor: r.floor,
					room_type: r.room_type,
					room_count: r.room_count,
					beds_per_room: r.beds_per_room,
					generate_beds: r.generate_beds,
					starting_room_number: r.starting,
				})),
			});
		},
		secondary_action_label: __("← Back"),
		secondary_action() { d3.hide(); showStep2(frm, step1Values, step2Values); },
	});
	d3.show();
}

// ---------------------------------------------------------------------------
// Apply wizard values — update floor_plan child table and trigger generation
// ---------------------------------------------------------------------------
function _generateRoomsAndBeds(frm, confirm_new_rooms) {
	frappe.call({
		method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
		args: { building_name: frm.doc.name, confirm_new_rooms: confirm_new_rooms ? 1 : 0 },
		freeze: true,
		freeze_message: __("Generating Rooms & Beds…"),
		callback: function (r) {
			if (r.exc) return;
			const m = r.message || {};
			// Re-run added new rooms/beds beyond what exists: confirm before creating
			// so the building never grows silently from an edited floor plan.
			if (m.needs_confirmation && !confirm_new_rooms) {
				frappe.confirm(
					__("The floor plan adds {0} new room(s) and {1} new bed(s) beyond what already exists. Existing rooms were updated to match the plan. Create the new rooms and beds?", [m.pending_new_rooms || 0, m.pending_new_beds || 0]),
					function () { _generateRoomsAndBeds(frm, 1); },
					function () { frm.reload_doc(); }
				);
			} else {
				frm.reload_doc();
			}
		},
		error: function () {
			frappe.show_alert({
				message: __("Could not complete the generation. Please try again."),
				indicator: "red",
			});
		}
	});
}

function _applyWizard(frm, v) {
	// v = { abbreviation, rows: [{floor, room_type, room_count, beds_per_room, generate_beds, starting_room_number}] }
	function _buildAndSave() {
		frm.doc.floor_plan = [];
		v.rows.forEach(row => {
			let childRow = frm.add_child("floor_plan");
			childRow.floor_number = row.floor;
			childRow.room_count = row.room_count;
			childRow.bed_capacity_per_room = row.beds_per_room;
			childRow.room_type = row.room_type;
			childRow.generate_beds = row.generate_beds ? 1 : 0;
			childRow.starting_room_number = row.starting_room_number || 1;
		});
		frm.refresh_field("floor_plan");
		frm.save("Update", function () {
			frappe.call({
				method: "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.generate_rooms_and_beds",
				args: { building_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Generating Rooms & Beds…"),
				callback: function (r) { if (!r.exc) frm.reload_doc(); },
				error: function () {
					frappe.show_alert({
						message: __("Could not generate rooms and beds. Please try again."),
						indicator: "red",
					});
				}
			});
		});
	}

	if (v.abbreviation && v.abbreviation !== frm.doc.abbreviation) {
		frappe.db.set_value("Accommodation Building", frm.doc.name, "abbreviation", v.abbreviation).then(() => {
			frm.doc.abbreviation = v.abbreviation;
			_buildAndSave();
		}).catch(() => {
			frappe.show_alert({
				message: __("Could not save the building abbreviation. Please try again."),
				indicator: "red",
			});
		});
	} else {
		_buildAndSave();
	}
}
