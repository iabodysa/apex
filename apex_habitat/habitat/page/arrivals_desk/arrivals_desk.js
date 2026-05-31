// Arrivals Desk — unified "worker arrival" desk page (MVP).
//
// Standard Frappe page. No SPA / Vue / React / external libraries: built from
// frappe.ui.Page primitives + native frappe.ui.Dialog, exactly like the Front
// Desk board. The server is the source of truth: every tile calls an EXISTING
// whitelisted endpoint (the page adds zero new write logic), and after every
// write we RE-FETCH get_arrival_card rather than mutating chips optimistically.
//
// Endpoints reused (no new business logic):
//   House     -> apex_habitat.habitat.api.front_desk.quick_check_in
//   Custody   -> apex_habitat.habitat.api.custody_kiosk.issue_cart
//   Masar     -> apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link
//   Transport -> frappe.new_doc("Transport Request", {...prefilled})
// Read-only card -> apex_habitat.habitat.api.arrivals_desk.get_arrival_card

frappe.pages["arrivals-desk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Arrivals Desk"),
		single_column: true,
	});

	const ad = new ArrivalsDesk(page);
	ad.setup();
};

class ArrivalsDesk {
	constructor(page) {
		this.page = page;
		this.employee = null;
		this.card = null;
	}

	setup() {
		this.$container = $('<div class="ad-board"></div>').appendTo(this.page.main);
		this._render_empty(__("Select a worker to begin arrival."));
		this._setup_controls();
	}

	_setup_controls() {
		// Worker selector in the page head.
		this.employee_field = this.page.add_field({
			fieldname: "employee",
			label: __("Worker"),
			fieldtype: "Link",
			options: "Employee",
			change: () => {
				const val = this.employee_field.get_value();
				if (val && val !== this.employee) {
					this.employee = val;
					this.refresh();
				} else if (!val && this.employee) {
					this.employee = null;
					this.card = null;
					this._render_empty(__("Select a worker to begin arrival."));
				}
			},
		});

		this.page.set_primary_action(__("Refresh"), () => {
			if (this.employee) {
				this.refresh();
			} else {
				frappe.show_alert({
					message: __("Select a worker to begin arrival."),
					indicator: "orange",
				});
			}
		}, "refresh");
	}

	refresh() {
		if (!this.employee) return;
		const requested = this.employee;
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.arrivals_desk.get_arrival_card",
			args: { employee: this.employee },
			callback: (r) => {
				// Ignore a stale response if the user switched workers mid-flight.
				if (requested !== this.employee) return;
				if (r.exc || !r.message) {
					this._render_error(__("Could not load the arrival card for this worker."));
					return;
				}
				this.card = r.message;
				this._render_card(r.message);
			},
			error: () => {
				if (requested !== this.employee) return;
				this._render_error(__("Could not load the arrival card. Check your connection and try again."));
			},
		});
	}

	_render_empty(message) {
		this.$container.empty();
		$('<div class="ad-empty text-muted"></div>').text(message).appendTo(this.$container);
	}

	_render_loading() {
		this.$container.empty();
		const $wrap = $('<div class="ad-loading" aria-busy="true"></div>').appendTo(this.$container);
		$('<div class="ad-loading-label text-muted"></div>')
			.text(__("Loading arrival card…"))
			.appendTo($wrap);
	}

	_render_error(message) {
		this.$container.empty();
		const $err = $('<div class="ad-error"></div>').appendTo(this.$container);
		$('<div class="ad-error-msg"></div>').text(message).appendTo($err);
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__("Retry"))
			.on("click", () => this.refresh())
			.appendTo($err);
	}

	_render_card(card) {
		this.$container.empty();

		// Identity card — photo + name + project.
		const $id = $('<div class="ad-identity"></div>').appendTo(this.$container);
		const photo = card.image
			? `<img class="ad-photo" src="${frappe.utils.escape_html(card.image)}" alt="" />`
			: `<div class="ad-photo ad-photo--empty">${__("No photo")}</div>`;
		$id.append(photo);
		const $meta = $('<div class="ad-identity-meta"></div>').appendTo($id);
		$('<div class="ad-identity-name"></div>')
			.text(card.employee_name || card.employee)
			.appendTo($meta);
		$('<div class="ad-identity-sub text-muted"></div>')
			.text(card.project ? `${__("Project")}: ${card.project}` : __("No project assigned yet"))
			.appendTo($meta);
		if (card.current_bed_code || card.current_building) {
			$('<div class="ad-identity-sub text-muted"></div>')
				.text(`${__("Current bed")}: ${card.current_bed_code || card.current_bed || "—"}`)
				.appendTo($meta);
		}

		// Four action tiles.
		const $tiles = $('<div class="ad-tiles"></div>').appendTo(this.$container);
		this._render_tile($tiles, {
			key: "house",
			label: __("House"),
			done: card.has_housing,
			done_text: __("Assigned"),
			pending_text: __("Not assigned"),
			handler: () => this._open_house_dialog(),
		});
		this._render_tile($tiles, {
			key: "custody",
			label: __("Custody"),
			done: card.has_custody,
			done_text: __("{0} items", [card.custody_count || 0]),
			pending_text: __("None issued"),
			handler: () => this._open_custody_dialog(),
		});
		this._render_tile($tiles, {
			key: "masar",
			label: __("Masar Link"),
			done: card.masar_enabled,
			done_text: __("Issued"),
			pending_text: __("Not issued"),
			// Tile 3 needs WRITE on Masar Worker Token — disable (fail soft) if missing.
			disabled: !frappe.perm.has_perm("Masar Worker Token", 0, "write"),
			disabled_text: __("You lack permission to issue links."),
			handler: () => this._open_masar_dialog(),
		});
		this._render_tile($tiles, {
			key: "transport",
			label: __("Transport"),
			done: false,
			done_text: "",
			pending_text: __("Request a ride"),
			// Tile 4 CREATEs a Transport Request — disable (fail soft) if missing.
			disabled: !frappe.model.can_create("Transport Request"),
			disabled_text: __("You lack permission to create transport requests."),
			handler: () => this._open_transport(),
		});
	}

	_render_tile($parent, opt) {
		const $tile = $(`<div class="ad-tile" tabindex="0" role="button"></div>`).appendTo($parent);
		$('<div class="ad-tile-label"></div>').text(opt.label).appendTo($tile);

		const chip_class = opt.done ? "ad-chip--done" : "ad-chip--pending";
		const chip_text = opt.done ? opt.done_text : opt.pending_text;
		if (chip_text) {
			$(`<div class="ad-chip ${chip_class}"></div>`).text(chip_text).appendTo($tile);
		}

		if (opt.disabled) {
			$tile.addClass("ad-tile--disabled").attr("aria-disabled", "true");
			$('<div class="ad-tile-note text-muted"></div>')
				.text(opt.disabled_text || __("Unavailable"))
				.appendTo($tile);
			return;
		}

		const handler = () => opt.handler();
		$tile.on("click", handler);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
	}

	// ── Tile 1: House (reuses front_desk.quick_check_in) ─────────────────────
	_open_house_dialog() {
		const employee = this.employee;
		const d = new frappe.ui.Dialog({
			title: __("Assign House"),
			fields: [
				{
					fieldname: "building",
					label: __("Building"),
					fieldtype: "Link",
					options: "Accommodation Building",
					reqd: 1,
					onchange: function () {
						const b = this.get_value && this.get_value();
						d.set_value("room", "");
						d.set_value("bed", "");
						d.fields_dict.room.get_query = () => ({ filters: b ? { building: b } : {} });
						d.fields_dict.bed.get_query = () => ({ filters: {} });
					},
				},
				{
					fieldname: "room",
					label: __("Room"),
					fieldtype: "Link",
					options: "Accommodation Room",
					reqd: 1,
					get_query: () => ({ filters: {} }),
					onchange: function () {
						const room = this.get_value && this.get_value();
						d.set_value("bed", "");
						d.fields_dict.bed.get_query = () => ({
							filters: room ? { room: room, status: ["!=", "Occupied"] } : {},
						});
					},
				},
				{
					fieldname: "bed",
					label: __("Bed"),
					fieldtype: "Link",
					options: "Accommodation Bed",
					reqd: 1,
					get_query: () => ({ filters: {} }),
				},
				{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", reqd: 1 },
				{
					fieldname: "check_in_date",
					label: __("Check-in Date"),
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
			],
			primary_action_label: __("Check In"),
			primary_action: (values) => {
				frappe.call({
					method: "apex_habitat.habitat.api.front_desk.quick_check_in",
					args: {
						bed: values.bed,
						employee: employee,
						project: values.project,
						check_in_date: values.check_in_date,
					},
					freeze: true,
					freeze_message: __("Checking in…"),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						// Remember the building so Custody defaults to it (step 1 → step 2).
						this._last_building = values.building;
						frappe.show_alert({
							message: __("Checked in: {0}", [r.message.assignment]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			},
		});
		// Default project from the existing card when known.
		if (this.card && this.card.project) d.set_value("project", this.card.project);
		d.show();
	}

	// ── Tile 2: Custody (reuses custody_kiosk.issue_cart) ────────────────────
	_open_custody_dialog() {
		const employee = this.employee;
		// Building defaults from step 1 (house assignment) or the worker's current bed.
		const default_building =
			this._last_building || (this.card && this.card.current_building) || null;
		const d = new frappe.ui.Dialog({
			title: __("Issue Custody"),
			fields: [
				{
					fieldname: "building",
					label: __("Building (source store)"),
					fieldtype: "Link",
					options: "Accommodation Building",
					reqd: 1,
					default: default_building,
				},
				{
					fieldname: "article",
					label: __("Article"),
					fieldtype: "Link",
					options: "Custody Article",
					reqd: 1,
				},
				{
					fieldname: "qty",
					label: __("Quantity"),
					fieldtype: "Int",
					reqd: 1,
					default: 1,
				},
			],
			primary_action_label: __("Issue"),
			primary_action: (values) => {
				const items_json = JSON.stringify([{ article: values.article, qty: values.qty }]);
				frappe.call({
					method: "apex_habitat.habitat.api.custody_kiosk.issue_cart",
					args: {
						employee: employee,
						building: values.building,
						items_json: items_json,
					},
					freeze: true,
					freeze_message: __("Issuing custody…"),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						frappe.show_alert({
							message: __("Custody issued: {0}", [r.message.custody_issue]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			},
		});
		d.show();
	}

	// ── Tile 3: Masar link (reuses issue_worker_link) ────────────────────────
	_open_masar_dialog() {
		const employee = this.employee;
		frappe.call({
			method:
				"apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link",
			args: { employee: employee, regenerate: 0 },
			freeze: true,
			freeze_message: __("Issuing worker link…"),
			callback: (r) => {
				if (r.exc || !r.message) return;
				ad_show_worker_link_dialog(r.message);
				this.refresh();
			},
		});
	}

	// ── Tile 4: Transport (prefilled new Transport Request) ──────────────────
	_open_transport() {
		const card = this.card || {};
		const workers = [{ employee: this.employee }];
		frappe.new_doc("Transport Request", {
			service_line: "Workers",
			project: card.project || undefined,
			accommodation_building:
				this._last_building || card.current_building || undefined,
			workers: workers,
		});
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// Masar worker-link result dialog. Same markup as the Accommodation Assignment
// form (QR data-URI inline + copy-link + wa.me share); no app-wide JS bundle is
// wired in hooks.py, so the helper is duplicated here. Keep the copies in sync.
// ─────────────────────────────────────────────────────────────────────────────

// Normalise a raw phone string to E.164 *digits* (no "+") suitable for wa.me,
// or return null if it can't confidently be normalised to >= 11 digits.
function ad_normalise_phone(raw) {
	if (!raw) return null;
	let digits = String(raw).replace(/[^0-9]/g, "");
	if (!digits) return null;
	if (digits.startsWith("00")) {
		digits = digits.slice(2);
	} else if (digits.startsWith("0")) {
		digits = "966" + digits.slice(1);
	} else if (digits.length === 9 && digits.startsWith("5")) {
		digits = "966" + digits;
	}
	return digits.length >= 11 ? digits : null;
}

function ad_show_worker_link_dialog(m) {
	const qr = m.qr
		? `<div style="text-align:center;margin:12px 0">
		     <img src="${m.qr}" alt="QR" style="width:200px;height:200px" />
		   </div>`
		: `<p style="color:#888">${__("QR rendering is unavailable on this site; share the link below.")}</p>`;
	const safe_link = frappe.utils.escape_html(m.link);

	const d = new frappe.ui.Dialog({
		title: __("Masar Worker Link"),
		indicator: "green",
	});
	d.$body.html(`
		<div>
			<p><b>${frappe.utils.escape_html(m.employee_name || m.employee)}</b></p>
			${qr}
			<p style="word-break:break-all">
				<a href="${safe_link}" target="_blank" rel="noopener">${safe_link}</a>
			</p>
			<p>
				<button class="btn btn-default btn-xs ad-copy-link">${__("Copy link")}</button>
			</p>
			<p style="color:#888;font-size:11px">
				${__("Anyone holding this link can view this worker's Masar app. Regenerate to revoke.")}
			</p>
		</div>`);

	d.$body.find(".ad-copy-link").on("click", () => {
		frappe.utils.copy_to_clipboard(m.link);
		frappe.show_alert({ message: __("Link copied."), indicator: "green" });
	});

	const phone = ad_normalise_phone(m.phone);
	if (phone) {
		d.set_primary_action(__("Send via WhatsApp"), () => {
			const text = __("Here is your personal Masar link: {0}", [m.link]);
			const url = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
			window.open(url, "_blank");
		});
	}
	d.show();
}
