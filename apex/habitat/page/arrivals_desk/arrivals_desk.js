// Copyright (c) 2026, afmcoltd

frappe.pages['arrivals-desk'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Arrivals Desk'),
		single_column: true,
	});
	wrapper.arrivals_desk = new ArrivalsDesk(page);
};

const AX_BED_PALETTE = {
	green: "background:var(--green-100);color:var(--green-700);border-color:var(--green-500);cursor:pointer;",
	red: "background:var(--red-100);color:var(--red-700);border-color:var(--red-500);cursor:pointer;",
	amber: "background:var(--yellow-100);color:var(--orange-700);border-color:var(--orange-500);",
	grey: "background:var(--gray-100);color:var(--gray-600);border-color:var(--gray-400);",
};
const AX_STYLE = {
	root:
		"position:relative;height:calc(100vh - var(--navbar-height) - var(--page-head-height) - 16px);min-block-size:420px;display:flex;flex-direction:column;",
	strip:
		"display:flex;gap:24px;flex-wrap:wrap;padding-block:8px;margin-block-end:8px;border-block-end:1px solid var(--border-color);",
	strip_stat: "display:flex;flex-direction:column;min-inline-size:96px;",
	strip_num: "font-size:1.6rem;font-weight:700;line-height:1.1;color:var(--heading-color);",
	strip_label: "font-size:0.8rem;color:var(--text-muted);",
	body:
		"display:grid;grid-template-columns:minmax(300px,26%) 1fr minmax(320px,28%);gap:12px;flex:1;min-block-size:0;overflow:hidden;",
	zone: "overflow-y:auto;min-inline-size:0;",
	zone_head:
		"position:sticky;inset-block-start:0;z-index:2;background:var(--fg-color);padding-block:6px;margin-block-end:8px;font-weight:700;color:var(--heading-color);border-block-end:1px solid var(--border-color);",
	zone_intake: "border-inline-end:1px solid var(--border-color);padding-inline-end:12px;",
	zone_floor: "display:flex;flex-direction:column;overflow:hidden;",
	zone_actions: "border-inline-start:1px solid var(--border-color);padding-inline-start:12px;",
	anchor: "display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px;padding-block-end:10px;margin-block-end:4px;",
	anchor_field: "flex:1 1 180px;min-inline-size:160px;",
	capacity: "flex:1 1 100%;display:flex;align-items:baseline;flex-wrap:wrap;gap:12px;min-block-size:22px;",
	cap_title: "font-weight:700;color:var(--heading-color);font-size:var(--text-lg);",
	cap_wrap: "flex:1 1 100%;display:flex;align-items:center;flex-wrap:wrap;gap:6px 12px;",
	cap_meter:
		"flex:1 1 160px;min-inline-size:120px;block-size:12px;display:flex;border-radius:6px;overflow:hidden;background:var(--gray-100);border:1px solid var(--border-color);",
	cap_fill: "block-size:100%;",
	cap_fill_free: "background:var(--green-500);",
	cap_fill_occ: "background:var(--red-500);",
	cap_fill_over:
		"background:var(--red-500);box-shadow:inset 0 0 0 2px var(--orange-500);",
	cap_legend: "font-size:var(--text-sm);color:var(--text-muted);display:inline-flex;align-items:center;gap:4px;",
	cap_swatch: "inline-size:10px;block-size:10px;border-radius:2px;display:inline-block;",
	stages: "flex:1 1 100%;display:flex;gap:6px;flex-wrap:wrap;",
	floor: "flex:1 1 auto;overflow-y:auto;padding-inline-end:6px;",
	floor_group: "margin-block-end:16px;",
	floor_header:
		"font-weight:700;color:var(--heading-color);border-block-end:1px solid var(--border-color);padding-block-end:4px;margin-block-end:8px;",
	rooms: "display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;",
	room: "border:1px solid var(--border-color);border-radius:8px;padding:8px;background:var(--card-bg);",
	room_same_project: "border-color:var(--primary);box-shadow:inset 0 0 0 1px var(--primary);",
	room_proj:
		"display:inline-block;margin-inline-start:6px;padding-block:0;padding-inline:5px;border-radius:3px;font-size:0.65rem;font-weight:700;color:var(--text-on-blue);background:var(--primary);vertical-align:middle;",
	room_header: "display:flex;justify-content:space-between;align-items:baseline;margin-block-end:6px;",
	room_number: "font-weight:600;",
	room_meta: "font-size:var(--text-xs);color:var(--text-muted);",
	room_oc:
		"appearance:none;margin-block-start:6px;inline-size:100%;font-size:var(--text-xs);font-weight:600;color:var(--primary);background:transparent;border:1px dashed var(--primary);border-radius:6px;padding-block:4px;padding-inline:6px;cursor:pointer;",
	beds: "display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:6px;",
	bed:
		"position:relative;border-radius:6px;padding-block:6px 5px;padding-inline:6px;min-block-size:72px;font-size:var(--text-sm);border:1px solid transparent;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;",
	bed_temp: "border-style:dashed;border-width:2px;",
	bed_busy: "pointer-events:none;opacity:0.75;",
	bed_code: "font-weight:700;",
	bed_occupant: "font-size:var(--text-xs);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;",
	bed_badge: "position:absolute;inset-block-start:3px;inset-inline-end:4px;font-size:var(--text-xs);",
	bed_blocker:
		"font-size:var(--text-xs);font-weight:600;color:var(--orange-700);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;",
	bed_chip:
		"display:inline-block;margin-inline-start:4px;padding-block:0;padding-inline:4px;border-radius:3px;font-size:0.65rem;font-weight:700;vertical-align:middle;",
	bed_chip_temp: "color:var(--orange-700);background:var(--yellow-100);border:1px solid var(--orange-500);",
	empty: "text-align:center;color:var(--text-muted);padding-block:48px;padding-inline:16px;",
	error_msg: "margin-block-end:10px;color:var(--red-700);",
	floor_banner:
		"margin-block-end:10px;padding-block:8px;padding-inline:12px;border-radius:6px;font-size:var(--text-sm);color:var(--orange-700);background:var(--yellow-100);border:1px solid var(--orange-500);",
	skeleton: "display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;",
	skeleton_room: "block-size:110px;border-radius:8px;background:var(--skeleton-bg);",
	search_input: "margin-block-end:8px;",
	results: "display:flex;flex-direction:column;gap:4px;",
	result:
		"display:flex;align-items:center;gap:8px;padding-block:6px;padding-inline:8px;border:1px solid var(--border-color);border-radius:6px;cursor:pointer;",
	result_active: "border-color:var(--primary);background:var(--bg-light-gray);",
	result_label: "font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	result_sub: "font-size:var(--text-xs);margin-inline-start:auto;flex:0 0 auto;",
	results_empty: "font-size:var(--text-sm);padding-block:8px;padding-inline:4px;",
	results_skeleton: "display:flex;flex-direction:column;gap:4px;",
	result_ghost: "block-size:34px;border-radius:6px;background:var(--skeleton-bg);",
	results_error:
		"display:flex;flex-direction:column;align-items:flex-start;gap:6px;padding:8px;border:1px solid var(--red-500);border-radius:6px;background:var(--red-100);",
	results_error_msg: "font-size:var(--text-sm);color:var(--red-700);",
	register_row: "margin-block-start:8px;inline-size:100%;text-align:start;",
	register_plus: "font-weight:700;color:var(--primary);",
	manifest: "margin-block-start:14px;",
	manifest_title: "font-weight:700;color:var(--heading-color);font-size:var(--text-sm);",
	manifest_tally: "font-size:var(--text-xs);margin-block-end:6px;",
	manifest_list: "display:flex;flex-direction:column;gap:3px;",
	manifest_row:
		"display:flex;align-items:center;gap:8px;padding-block:5px;padding-inline:8px;border:1px solid var(--border-color);border-radius:6px;cursor:pointer;",
	manifest_row_done: "background:var(--green-100);border-color:var(--green-500);",
	manifest_tick: "font-weight:700;",
	manifest_name: "font-weight:600;font-size:var(--text-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	manifest_sub: "font-size:var(--text-xs);margin-inline-start:auto;flex:0 0 auto;",
	active: "margin-block-start:14px;",
	active_card: "border:1px solid var(--primary);border-radius:8px;padding:10px;background:var(--card-bg);",
	active_card_load: "border-style:dashed;border-color:var(--border-color);",
	active_head: "display:flex;justify-content:space-between;align-items:center;gap:8px;",
	active_name: "font-weight:700;color:var(--heading-color);",
	active_sub: "font-size:var(--text-sm);margin-block-start:2px;",
	active_foot: "margin-block-start:8px;font-size:var(--text-sm);",
	active_hint: "color:var(--primary);font-weight:600;",
	active_bed: "font-weight:600;",
	cart: "margin-block-end:16px;",
	cart_title:
		"font-weight:700;color:var(--heading-color);font-size:var(--text-sm);border-block-end:1px solid var(--border-color);padding-block-end:4px;margin-block-end:6px;",
	cart_list: "display:flex;flex-direction:column;gap:3px;",
	cart_item:
		"display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px 8px;padding-block:4px;padding-inline:8px;border-radius:6px;background:var(--bg-light-gray);border-inline-start:3px solid transparent;",
	cart_item_done: "background:var(--green-100);border-inline-start-color:var(--green-500);",
	cart_name: "font-weight:600;font-size:var(--text-sm);",
	cart_bed: "font-size:var(--text-xs);",
	cart_dots: "flex:1 1 100%;display:flex;flex-wrap:wrap;gap:4px 10px;",
	cart_dot: "font-size:var(--text-xs);color:var(--text-muted);",
	cart_dot_on: "font-size:var(--text-xs);color:var(--green-700);font-weight:600;",
	cart_dot_off: "font-size:var(--text-xs);color:var(--orange-700);",
	cart_dot_na: "font-size:var(--text-xs);color:var(--text-muted);opacity:0.6;",
	deck_sec: "margin-block-end:12px;",
	deck_head:
		"font-weight:700;color:var(--heading-color);font-size:var(--text-sm);border-block-end:1px solid var(--border-color);padding-block-end:4px;margin-block-end:6px;",
	deck_list: "display:flex;flex-direction:column;gap:4px;",
	deck_row: "display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-block-size:36px;padding-block:4px;",
	deck_name: "font-weight:600;font-size:var(--text-sm);flex:1 1 auto;",
	tr_row: "display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-block-size:36px;padding-block:4px;cursor:pointer;margin:0;",
	tr_go: "margin-block-start:6px;inline-size:100%;",
	tr_note: "font-size:var(--text-sm);padding-block:4px;",
	custody_cart:
		"inline-size:100%;margin-block-start:6px;padding:6px;border:1px solid var(--border-color);border-radius:var(--border-radius);background:var(--bg-light-gray);",
	custody_lines: "display:flex;flex-direction:column;gap:2px;margin-block-end:6px;",
	custody_line: "display:flex;justify-content:space-between;align-items:center;font-size:var(--text-sm);",
	custody_add: "display:flex;gap:4px;align-items:center;",
	custody_article: "flex:1 1 auto;min-inline-size:0;",
	custody_qty: "inline-size:64px;flex:0 0 auto;",
	custody_foot: "margin-block-start:6px;",
	custody_issue_btn: "inline-size:100%;",
	catalog_error:
		"display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-block:6px;padding-inline:8px;margin-block-end:6px;border-radius:6px;font-size:var(--text-sm);color:var(--red-700);background:var(--red-100);border:1px solid var(--red-500);",
	qr_all: "inline-size:100%;margin-block-start:6px;",
	qr_pending:
		"display:flex;align-items:center;justify-content:center;gap:8px;font-size:var(--text-sm);color:var(--text-muted);padding-block:12px;",
	qr_spinner:
		"inline-size:16px;block-size:16px;border-radius:50%;border:2px solid var(--gray-400);border-block-start-color:var(--primary);display:inline-block;",
	qr_block: "display:flex;flex-direction:column;gap:10px;margin-block-start:8px;",
	qr_item: "border:1px solid var(--border-color);border-radius:var(--border-radius);padding:8px;text-align:center;background:var(--card-bg);",
	qr_name: "font-weight:600;font-size:var(--text-sm);margin-block-end:4px;",
	qr_img: "inline-size:120px;block-size:120px;",
	qr_link: "display:block;font-size:var(--text-xs);word-break:break-all;margin-block-start:4px;",
};
const AX_STEP = {
	base:
		"appearance:none;display:inline-flex;align-items:center;gap:6px;padding-block:4px;padding-inline:6px 10px;border-radius:14px;border:1px solid var(--border-color);background:var(--card-bg);font-size:var(--text-sm);color:var(--text-muted);",
	done: "border-color:var(--green-500);color:var(--green-700);cursor:pointer;",
	now: "border-color:var(--primary);color:var(--primary);",
	todo: "cursor:default;",
};
const AX_STEP_NUM = {
	base:
		"display:inline-flex;align-items:center;justify-content:center;inline-size:20px;block-size:20px;border-radius:50%;font-size:var(--text-xs);font-weight:700;",
	done: "background:var(--green-500);color:var(--text-on-blue);",
	now: "background:var(--primary);color:var(--text-on-blue);",
	todo: "background:var(--gray-100);color:var(--gray-600);",
};
function ax_bed_style(color, opts) {
	opts = opts || {};
	return (
		AX_STYLE.bed +
		(AX_BED_PALETTE[color] || AX_BED_PALETTE.grey) +
		(opts.temp ? AX_STYLE.bed_temp : "") +
		(opts.busy ? AX_STYLE.bed_busy : "")
	);
}

class ArrivalsDesk {
	constructor(page) {
		this.page = page;
		this.building = null;
		this.project = null;
		this.grid = null;
		this.active = null;
		this.cart = [];
		this.custodyIssued = false;
		this.cardIssued = false;
		this.transportStarted = false;
		/* Held as the promise, not as the flag it resolves to. A clerk who opens the register
		   modal before this call lands read `false` and got no passport scanner at all, with
		   nothing to retry — and the faster the clerk, the more likely it was. */
		this.mrzOcrEnabled = frappe
			.xcall('apex.habitat.api.arrivals_desk.get_intake_settings')
			.then((r) => !!(r && r.enable_passport_mrz_ocr))
			.catch(() => false);
		this.page.hide_form();
		this._build_skeleton();
		this._setup_anchor();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		this._watch_transport_saved();
		this._load_strip();
		this._render_empty(__('Pick a building to start the arrival.'));
	}

	_build_skeleton() {
		this.$root = $('<div class="arrivals-desk"></div>').attr('style', AX_STYLE.root).appendTo(this.page.main);
		this._build_strip();
		this.$body = $('<div class="ax-body"></div>').attr('style', AX_STYLE.body).appendTo(this.$root);

		this.$intake = $('<aside class="ax-zone ax-zone-intake"></aside>')
			.attr('style', AX_STYLE.zone + AX_STYLE.zone_intake)
			.appendTo(this.$body);
		$('<div class="ax-zone-head"></div>').attr('style', AX_STYLE.zone_head).text(__('Who is arriving?')).appendTo(this.$intake);

		this.$floorZone = $('<section class="ax-zone ax-zone-floor"></section>')
			.attr('style', AX_STYLE.zone + AX_STYLE.zone_floor)
			.appendTo(this.$body);
		this.$anchor = $('<div class="ax-anchor ax-zone-head"></div>')
			.attr('style', AX_STYLE.zone_head + AX_STYLE.anchor)
			.appendTo(this.$floorZone);
		this.$capacity = $('<div class="ax-capacity"></div>').attr('style', AX_STYLE.capacity).appendTo(this.$anchor);
		this.$stages = $('<div class="ax-stages"></div>').attr('style', AX_STYLE.stages).appendTo(this.$anchor);
		this.$floor = $('<div class="ax-floor"></div>').attr('style', AX_STYLE.floor).appendTo(this.$floorZone);
		this.$floor.on('click', '.ax-bed', (e) => this._on_bed_click(e));
		this.$floor.on('click', '.ax-room-oc', (e) => {
			e.stopPropagation();
			this._house_over_capacity($(e.currentTarget).attr('data-room'));
		});
		this.$floor.on('keydown', '.ax-bed--green, .ax-bed--red', (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				this._on_bed_click(e);
			}
		});

		this.$actions = $('<aside class="ax-zone ax-zone-actions"></aside>')
			.attr('style', AX_STYLE.zone + AX_STYLE.zone_actions)
			.appendTo(this.$body);
		$('<div class="ax-zone-head"></div>').attr('style', AX_STYLE.zone_head).text(__('This session')).appendTo(this.$actions);

		this._build_intake();
	}

	_build_strip() {
		this.$strip = $('<div class="ax-strip" role="status" aria-live="polite"></div>').attr('style', AX_STYLE.strip).appendTo(this.$root);
		const stat = (key, label) => {
			const $cell = $('<div class="ax-strip-stat"></div>').attr('style', AX_STYLE.strip_stat).appendTo(this.$strip);
			$('<div class="ax-strip-num">—</div>').attr('style', AX_STYLE.strip_num).appendTo($cell).attr('data-stat', key);
			$('<div class="ax-strip-label"></div>').attr('style', AX_STYLE.strip_label).text(label).appendTo($cell);
		};
		stat('arrivals_today', __('Arrivals today'));
		stat('pending_on_manifest', __('Pending on manifest'));
	}

	_load_strip() {
		const set = (key, val) =>
			this.$strip.find(`[data-stat="${key}"]`).text(cint(val) || 0);
		const num = (r) => (r && typeof r === 'object' ? r.value : r);
		frappe
			.xcall('apex.habitat.api.dashboard.get_arrivals_today')
			.then((v) => set('arrivals_today', num(v)))
			.catch(() => {});
		frappe
			.xcall('apex.habitat.api.dashboard.get_pending_on_manifest')
			.then((v) => set('pending_on_manifest', num(v)))
			.catch(() => {});
	}

	_setup_anchor() {
		const $bWrap = $('<div class="ax-anchor-field"></div>').attr('style', AX_STYLE.anchor_field).prependTo(this.$anchor);
		const $pWrap = $('<div class="ax-anchor-field"></div>').attr('style', AX_STYLE.anchor_field).insertAfter($bWrap);

		this.building_field = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				fieldname: 'building',
				options: 'Building',
				label: __('Building'),
				placeholder: __('Pick a building…'),
				get_query: () => ({
					query: 'apex.habitat.api.arrivals_desk.buildings_with_capacity',
				}),
				onchange: () => this._on_building_change(),
			},
			parent: $bWrap.get(0),
			render_input: true,
		});
		this.building_field.refresh();

		this.project_field = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				fieldname: 'project',
				options: 'Project',
				label: __('Project'),
				placeholder: __('Pick a project…'),
				onchange: () => this._on_project_change(),
			},
			parent: $pWrap.get(0),
			render_input: true,
		});
		this.project_field.refresh();

		if (this.building_field.$input) {
			this.building_field.$input.on('change awesomplete-selectcomplete', () => this._on_building_change());
		}
		if (this.project_field.$input) {
			this.project_field.$input.on('change awesomplete-selectcomplete', () => this._on_project_change());
		}
	}

	_on_building_change() {
		const val = this.building_field.get_value();
		if (val && val !== this.building) {
			this.building = val;
			this.catalog = null;
			this._clear_deck();
			this.refresh();
			this._load_catalog();
			this._load_manifest();
		} else if (!val && this.building) {
			this.building = null;
			this.grid = null;
			this.catalog = null;
			this._clear_deck();
			this._render_stages();
			this._render_capacity(null);
			this._render_empty(__('Pick a building to start the arrival.'));
			this._load_manifest();
		}
	}

	_on_project_change() {
		this.project = this.project_field.get_value() || null;
		if (this.grid) this._render_grid(this.grid);
	}

	refresh() {
		this._load_strip();
		if (!this.building) return;
		const requested = this.building;
		this._render_loading();
		frappe
			.call({
				method: 'apex.habitat.api.front_desk.get_building_grid',
				args: { building: this.building },
			})
			.then((r) => {
				if (this.building !== requested) return;
				this.grid = r.message;
				this._render_grid(this.grid);
			})
			.catch(() => {
				if (this.building !== requested) return;
				this._render_error();
			});
	}

	_build_intake() {
		const $search = $('<div class="ax-search"></div>').appendTo(this.$intake);
		this.$search_input = $(
			`<input type="search" class="ax-search-input form-control form-control-sm" style="${AX_STYLE.search_input}" placeholder="${__(
				'Search worker name or passport…'
			)}" />`
		).appendTo($search);
		this.$results = $('<div class="ax-results"></div>').attr('style', AX_STYLE.results).appendTo($search);
		this.$manifest = $('<div class="ax-manifest"></div>').attr('style', AX_STYLE.manifest).appendTo(this.$intake);
		this.$active = $('<div class="ax-active"></div>').attr('style', AX_STYLE.active).appendTo(this.$intake);
		this.$cart = $('<div class="ax-cart"></div>').attr('style', AX_STYLE.cart).appendTo(this.$actions);
		this.$deck = $('<div class="ax-deck"></div>').appendTo(this.$actions);
		this.$search_input.on('input', frappe.utils.debounce(() => this._search(), 250));
		this._render_results(null);
		this._render_cart();
		this._load_manifest();
	}

	_load_manifest() {
		if (!this.$manifest) return;
		frappe
			.call({
				method: 'apex.habitat.api.arrivals_desk.get_expected_arrivals',
				args: { building: this.building },
			})
			.then((r) => this._render_manifest(r.message))
			.catch(() => this.$manifest.empty());
	}

	_render_manifest(data) {
		this.$manifest.empty();
		const workers = (data && data.workers) || [];
		if (!workers.length) return;
		$('<div class="ax-manifest-title"></div>')
			.attr('style', AX_STYLE.manifest_title)
			.text(__("Today's expected arrivals ({0})", [data.total]))
			.appendTo(this.$manifest);
		$('<div class="ax-manifest-tally text-muted"></div>')
			.attr('style', AX_STYLE.manifest_tally)
			.text(__('{0} of {1} arrived, {2} pending', [data.arrived, data.total, data.pending]))
			.appendTo(this.$manifest);
		const $list = $('<div class="ax-manifest-list"></div>').attr('style', AX_STYLE.manifest_list).appendTo(this.$manifest);
		workers.forEach((w) => this._manifest_row($list, w));
	}

	_manifest_row($list, w) {
		const $row = $(`<div class="ax-manifest-row${w.arrived ? ' ax-manifest-row--done' : ''}" tabindex="0" role="button"></div>`)
			.attr('style', AX_STYLE.manifest_row + (w.arrived ? AX_STYLE.manifest_row_done : ''))
			.appendTo($list);
		$('<span class="ax-manifest-tick"></span>')
			.attr('style', AX_STYLE.manifest_tick + (w.arrived ? 'color:var(--green-700);' : 'color:var(--text-muted);'))
			.text(w.arrived ? '✓' : '○')
			.appendTo($row);
		$('<span class="ax-manifest-name"></span>').attr('style', AX_STYLE.manifest_name).text(w.worker_name || '').appendTo($row);
		if (w.passport_number) {
			$('<span class="ax-manifest-sub text-muted"></span>')
				.attr('style', AX_STYLE.manifest_sub)
				.html(`<bdi>${frappe.utils.escape_html(w.passport_number)}</bdi>`)
				.appendTo($row);
		}
		const act = () => this._pick_manifest(w);
		$row.on('click', act);
		$row.on('keydown', (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				act();
			}
		});
	}

	_pick_manifest(w) {
		if (w.temporary_worker) {
			this._select_worker({
				party_type: 'Temporary Worker',
				party: w.temporary_worker,
				label: w.worker_name,
			});
			return;
		}
		this._open_register_modal({
			worker_name: w.worker_name,
			passport_number: w.passport_number,
			nationality: w.nationality,
			labour_supplier: w.labour_supplier,
			project: w.project,
			batch_row: w.row,
		});
	}

	_search() {
		const txt = (this.$search_input.val() || '').trim();
		this._searched = true;
		this._render_search_skeleton();
		frappe
			.call({
				method: 'apex.habitat.api.arrivals_desk.search_arrivals_workers',
				args: { building: this.building, txt },
			})
			.then((r) => this._render_results(r.message || []))
			.catch(() => this._render_search_error());
	}

	_render_search_skeleton() {
		this.$results.html(
			`<div class="ax-results-skeleton" aria-hidden="true" style="${AX_STYLE.results_skeleton}">` +
				`<div class="ax-result-ghost" style="${AX_STYLE.result_ghost}"></div>`.repeat(3) +
				'</div>'
		);
	}

	_render_search_error() {
		this.$results.empty();
		const $row = $('<div class="ax-results-error"></div>').attr('style', AX_STYLE.results_error).appendTo(this.$results);
		$('<div class="ax-results-error-msg"></div>')
			.attr('style', AX_STYLE.results_error_msg)
			.text(__('Search failed. Please retry.'))
			.appendTo($row);
		$('<button class="btn btn-default btn-sm ax-results-retry"></button>')
			.text(__('Retry'))
			.on('click', () => this._search())
			.appendTo($row);
		this._append_register_row();
	}

	_render_results(rows) {
		this.$results.empty();
		if (rows && rows.length) {
			rows.forEach((row) => this._result_row(row));
		} else {
			const msg = this._searched
				? __('No registered workers match. Register a new arrival below.')
				: __('Search a name or passport, or register a new arrival');
			$('<div class="ax-results-empty text-muted"></div>').attr('style', AX_STYLE.results_empty).text(msg).appendTo(this.$results);
		}
		this._append_register_row();
	}

	_append_register_row() {
		$('<button class="btn btn-default btn-sm ax-register-row"></button>')
			.attr('style', AX_STYLE.register_row)
			.html(`<span class="ax-register-plus" style="${AX_STYLE.register_plus}">+</span> ${__('Register new arrival by passport')}`)
			.on('click', () => this._open_register_modal())
			.appendTo(this.$results);
	}

	_result_row(row) {
		const is_tw = row.party_type === 'Temporary Worker';
		const $row = $(
			`<div class="ax-result" tabindex="0" role="button" style="${AX_STYLE.result}">` +
				`<span class="indicator-pill no-indicator-dot ${is_tw ? 'orange' : 'green'}">${
					is_tw ? __('Temp') : __('Emp')
				}</span>` +
				`<span class="ax-result-label" style="${AX_STYLE.result_label}">${frappe.utils.escape_html(row.label || '')}</span>` +
				`<span class="ax-result-sub text-muted" style="${AX_STYLE.result_sub}"><bdi>${frappe.utils.escape_html(row.sub || '')}</bdi></span>` +
				`${this._expiry_chip(row)}</div>`
		).appendTo(this.$results);
		const pick = () => {
			this.$results.find('.ax-result').removeClass('ax-result--active').attr('style', AX_STYLE.result);
			$row.addClass('ax-result--active').attr('style', AX_STYLE.result + AX_STYLE.result_active);
			this._select_worker(row);
		};
		$row.on('click', pick);
		$row.on('keydown', (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				pick();
			}
		});
	}

	_select_worker(row) {
		this.active = { party_type: row.party_type, party: row.party, label: row.label };
		this.$active.html(
			`<div class="ax-active-card ax-active-card--load text-muted" style="${AX_STYLE.active_card + AX_STYLE.active_card_load}">${__(
				'Loading…'
			)}</div>`
		);
		frappe
			.call({
				method: 'apex.habitat.api.arrivals_desk.get_arrival_card',
				args: { party_type: row.party_type, party: row.party },
			})
			.then((r) => this._render_active_card(r.message))
			.catch(() => this._render_active_card_error(row));
	}

	_render_active_card_error(row) {
		const $card = $('<div class="ax-active-card ax-active-card--err"></div>')
			.attr('style', AX_STYLE.active_card)
			.appendTo(this.$active.empty());
		$('<div class="text-muted"></div>').text(__('Could not load the worker.')).appendTo($card);
		$('<button class="btn btn-default btn-xs ax-active-retry"></button>')
			.text(__('Retry'))
			.on('click', () => this._select_worker(row))
			.appendTo($card);
	}

	_expiry_chip(item) {
		const d = item && item.expiry_days;
		if (d === null || d === undefined) return '';
		if (d < 0) {
			return `<span class="indicator-pill no-indicator-dot red">${__('Window expired {0}d ago', [
				Math.abs(d),
			])}</span>`;
		}
		return `<span class="indicator-pill no-indicator-dot orange">${__('Window ends in {0}d', [
			d,
		])}</span>`;
	}

	_render_active_card(card) {
		if (!card) {
			this.$active.empty();
			return;
		}
		const is_tw = card.party_type === 'Temporary Worker';
		const bed = card.current_bed_code || card.current_bed || '';
		const foot = card.has_housing
			? `<span class="ax-active-bed" style="${AX_STYLE.active_bed}">${__('Bed')}: <bdi>${frappe.utils.escape_html(bed)}</bdi></span>`
			: `<span class="ax-active-hint" style="${AX_STYLE.active_hint}">${__('Click a free bed to house him.')}</span>`;
		this.$active.html(
			`<div class="ax-active-card" style="${AX_STYLE.active_card}"><div class="ax-active-head" style="${AX_STYLE.active_head}">` +
				`<span class="ax-active-name" style="${AX_STYLE.active_name}">${frappe.utils.escape_html(card.worker_name || card.party)}</span>` +
				`<span class="indicator-pill no-indicator-dot ${is_tw ? 'orange' : 'green'}">${
					is_tw ? __('Temporary Worker') : __('Employee')
				}</span>${this._expiry_chip(card)}</div>` +
				`<div class="ax-active-sub text-muted" style="${AX_STYLE.active_sub}">${
					card.project ? frappe.utils.escape_html(card.project) : __('No project yet')
				}</div>` +
				`<div class="ax-active-foot" style="${AX_STYLE.active_foot}">${foot}</div></div>`
		);
	}

	_open_register_modal(prefill) {
		const pf = prefill || {};
		const d = new frappe.ui.Dialog({
			title: __('Register New Arrival (Passport)'),
			fields: [
				{ fieldname: 'mrz_scan', fieldtype: 'HTML' },
				{ fieldname: 'worker_name', label: __('Worker Name'), fieldtype: 'Data', reqd: 1, default: pf.worker_name },
				{ fieldname: 'passport_number', label: __('Passport Number'), fieldtype: 'Data', reqd: 1, default: pf.passport_number },
				{ fieldname: 'cb1', fieldtype: 'Column Break' },
				{ fieldname: 'nationality', label: __('Nationality'), fieldtype: 'Data', default: pf.nationality },
				{ fieldname: 'labour_supplier', label: __('Labour Supplier'), fieldtype: 'Data', default: pf.labour_supplier },
				{ fieldname: 'sb1', fieldtype: 'Section Break' },
				{
					fieldname: 'building',
					label: __('Building'),
					fieldtype: 'Link',
					options: 'Building',
					default: this.building,
				},
				{
					fieldname: 'project',
					label: __('Project'),
					fieldtype: 'Link',
					options: 'Project',
					default: pf.project || this.project,
				},
				{ fieldname: 'cb2', fieldtype: 'Column Break' },
				{ fieldname: 'cell_number', label: __('Cell Number'), fieldtype: 'Data' },
				{ fieldname: 'iqama_number', label: __('Iqama Number (if any)'), fieldtype: 'Data' },
			],
			primary_action_label: __('Register'),
			primary_action: (values) => {
				frappe.call({
					method: 'apex.habitat.api.arrivals_desk.register_temporary_worker',
					args: { ...values, batch_row: pf.batch_row || null },
					freeze: true,
					freeze_message: __('Registering…'),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						frappe.show_alert({ message: __('Registered: {0}', [r.message.label]), indicator: 'green' });
						this._select_worker(r.message);
						this._search();
						this._load_manifest();
					},
				});
			},
		});
		d.$wrapper.addClass('ax-register-modal');
		d.show();
		this.mrzOcrEnabled.then((enabled) => {
			if (enabled && d.$wrapper.is(':visible')) this._render_mrz_scan(d);
		});
	}

	_render_mrz_scan(d) {
		const $wrap = $(d.get_field('mrz_scan').wrapper);
		$wrap.empty();
		const $box = $('<div class="ax-mrz-scan"></div>').appendTo($wrap);
		const $input = $('<input type="file" accept="image/*" capture="environment" class="ax-mrz-input" />').appendTo($box);
		$('<button class="btn btn-sm btn-default ax-mrz-btn"></button>')
			.text(__('Scan passport (MRZ)'))
			.on('click', () => $input.trigger('click'))
			.appendTo($box);
		const $status = $('<span class="ax-mrz-status"></span>').appendTo($box);
		$input.on('change', (e) => {
			const file = e.target.files && e.target.files[0];
			if (!file) return;
			const reader = new FileReader();
			reader.onload = () => this._scan_passport(d, reader.result, $status);
			reader.readAsDataURL(file);
		});
	}

	_scan_passport(d, dataUrl, $status) {
		$status.text(__('Reading passport…'));
		frappe.call({
			method: 'apex.habitat.api.arrivals_desk.parse_passport',
			args: { image: dataUrl },
			callback: (r) => {
				if (r.exc) {
					$status.text(__('Could not read the passport — enter the details manually.'));
					return;
				}
				const res = r.message || {};
				if (res.ok && res.fields) {
					Object.keys(res.fields).forEach((k) => {
						if (d.get_field(k)) d.set_value(k, res.fields[k]);
					});
					$status.text(__('Pre-filled — please verify.'));
				} else if (res.reason === 'ocr_unavailable') {
					$status.text(__('OCR engine not available — enter the details manually.'));
				} else {
					$status.text(__('Could not read the passport — enter the details manually.'));
				}
			},
			error: () => $status.text(__('Scan failed — enter the details manually.')),
		});
	}

	_on_bed_click(e) {
		const $bed = $(e.currentTarget);
		if ($bed.hasClass('ax-bed--red')) {
			this._open_check_out($bed.attr('data-bed'), $bed);
			return;
		}
		if (!$bed.hasClass('ax-bed--green')) return;
		if (!this.active) {
			frappe.show_alert({ message: __('Pick a worker first.'), indicator: 'orange' });
			return;
		}
		if (!this.project) {
			frappe.show_alert({ message: __('Pick a project first.'), indicator: 'orange' });
			return;
		}
		this._house_in_bed($bed.attr('data-bed'), $bed);
	}

	_bed_occupant(bed) {
		let found = null;
		(this.grid && this.grid.floors ? this.grid.floors : []).forEach((floor) =>
			(floor.rooms || []).forEach((room) =>
				(room.beds || []).forEach((b) => {
					if (b.bed === bed) found = b.occupant || null;
				})
			)
		);
		return found;
	}

	_open_check_out(bed, $bed) {
		const occupant = this._bed_occupant(bed) || {};
		if (occupant.has_custody) {
			apex.habitat.custody_block_dialog(occupant.assignment);
			return;
		}
		apex.habitat.quick_checkout_dialog(
			{ bed, employee_name: occupant.employee_name },
			(state) => {
				if ($bed && $bed.length) {
					$bed.toggleClass('ax-bed--busy', state).attr('style', ax_bed_style('red', state ? { busy: true } : undefined));
				}
			},
			() => this.refresh()
		);
	}

	_capture_terms_signature(worker, on_done) {
		const dialog = new frappe.ui.Dialog({
			title: __('Housing Terms — {0}', [worker.label || worker.party]),
			fields: [
				{
					fieldname: 'terms_signature',
					fieldtype: 'Signature',
					label: __('Sign to accept the housing terms'),
				},
			],
			primary_action_label: __('Accept & House'),
			primary_action: () => {
				const sig = dialog.get_value('terms_signature');
				dialog.hide();
				on_done(sig || null);
			},
			secondary_action_label: __('Skip'),
			secondary_action: () => {
				dialog.hide();
				on_done(null);
			},
		});
		dialog.show();
	}

	_house_in_bed(bed, $bed) {
		this._capture_terms_signature(this.active, (terms_signature) =>
			this._do_house_in_bed(bed, $bed, terms_signature)
		);
	}

	_do_house_in_bed(bed, $bed, terms_signature) {
		const worker = this.active;
		if ($bed && $bed.length) {
			$bed.removeClass('ax-bed--green')
				.addClass('ax-bed--red ax-bed--busy')
				.attr('style', ax_bed_style('red', { busy: true }))
				.removeAttr('tabindex role');
		}
		const rollback = () => {
			if ($bed && $bed.length) {
				$bed.removeClass('ax-bed--red ax-bed--busy')
					.addClass('ax-bed--green')
					.attr('style', ax_bed_style('green'))
					.attr({ tabindex: 0, role: 'button' });
			}
		};
		frappe.call({
			method: 'apex.habitat.api.front_desk.quick_check_in',
			args: {
				bed,
				party_type: worker.party_type,
				party: worker.party,
				project: this.project,
				check_in_date: frappe.datetime.get_today(),
				terms_signature: terms_signature || null,
			},
			callback: (r) => {
				if (r.exc || !r.message) {
					rollback();
					return;
				}
				if ($bed && $bed.length) $bed.removeClass('ax-bed--busy').attr('style', ax_bed_style('red'));
				frappe.show_alert({ message: __('Housed {0}', [worker.label]), indicator: 'green' });
				const dupe = this.cart.some(
					(c) => c.party === worker.party && c.party_type === worker.party_type
				);
				if (!dupe) this.cart.push({ ...worker, bed: r.message.bed || bed });
				this._clear_active(true);
				this._render_cart();
				this._reload_after_housing();
			},
			error: () => rollback(),
		});
	}

	/* The highlight is derived from the selection, so the two places that drop the worker
	   cannot leave a row lit behind them. A lit row with nothing selected tells the clerk
	   they are still working on someone they have already housed. */
	_clear_deck() {
		this.cart = [];
		this.custodyIssued = false;
		this._clear_active(true);
		this._render_deck();
	}

	_clear_active(clearPane) {
		this.active = null;
		if (this.$results) {
			this.$results.find('.ax-result').removeClass('ax-result--active').attr('style', AX_STYLE.result);
		}
		if (clearPane && this.$active) this.$active.empty();
	}

	/* The board is re-read from the server after a housing, never patched in place.
	   The patch that used to live here built an occupant out of the three fields the clerk
	   had typed, so the bed it lit carried no has_custody and no assignment. _open_check_out
	   reads exactly those, which meant the custody block could not fire for anyone housed in
	   the current session: the clerk checked them out and the kit left with them. A round
	   trip is slower on a tablet, and that is the trade. */
	_reload_after_housing() {
		if (!this.building) return;
		const requested = this.building;
		frappe
			.call({
				method: 'apex.habitat.api.front_desk.get_building_grid',
				args: { building: this.building },
			})
			.then((r) => {
				if (this.building !== requested || r.exc || !r.message) return;
				this.grid = r.message;
				this._render_grid(this.grid);
				this._load_manifest();
				this._load_strip();
			})
			.catch(() => {});
	}

	_house_over_capacity(room) {
		if (!this.active) {
			frappe.show_alert({ message: __('Pick a worker first.'), indicator: 'orange' });
			return;
		}
		if (!this.project) {
			frappe.show_alert({ message: __('Pick a project first.'), indicator: 'orange' });
			return;
		}
		const worker = this.active;
		frappe.confirm(__('Room is full. House {0} in a temporary over-capacity bed?', [worker.label]), () => {
			frappe.call({
				method: 'apex.habitat.api.arrivals_desk.house_over_capacity',
				args: {
					room,
					party_type: worker.party_type,
					party: worker.party,
					project: this.project,
					check_in_date: frappe.datetime.get_today(),
				},
				freeze: true,
				freeze_message: __('Housing over capacity…'),
				callback: (r) => {
					if (r.exc || !r.message) return;
					frappe.show_alert({
						message: __('Housed {0} in a temporary bed', [worker.label]),
						indicator: 'green',
					});
					const dupe = this.cart.some(
						(c) => c.party === worker.party && c.party_type === worker.party_type
					);
					if (!dupe) this.cart.push({ ...worker, bed: r.message.bed_code || r.message.bed, temp: true });
					this._clear_active(true);
					this._render_cart();
					this.refresh();
				},
			});
		});
	}

	_render_cart() {
		this._render_deck();
		this.$cart.empty();
		if (!this.cart.length) return;
		$('<div class="ax-cart-title"></div>')
			.attr('style', AX_STYLE.cart_title)
			.text(__('Arrived this session ({0})', [this.cart.length]))
			.appendTo(this.$cart);
		const $list = $('<div class="ax-cart-list"></div>').attr('style', AX_STYLE.cart_list).appendTo(this.$cart);
		this.cart.forEach((c) => {
			const dots = this._cart_dots(c);
			const $item = $(`<div class="ax-cart-item${dots.complete ? ' ax-cart-item--done' : ''}"></div>`)
				.attr('style', AX_STYLE.cart_item + (dots.complete ? AX_STYLE.cart_item_done : ''))
				.html(
					`<span class="ax-cart-name" style="${AX_STYLE.cart_name}">${frappe.utils.escape_html(c.label || c.party)}</span>` +
						`<span class="ax-cart-bed text-muted" style="${AX_STYLE.cart_bed}"><bdi>${frappe.utils.escape_html(c.bed || '')}</bdi></span>`
				)
				.appendTo($list);
			$('<div class="ax-cart-dots"></div>').attr('style', AX_STYLE.cart_dots).html(dots.html).appendTo($item);
			$('<button class="btn btn-xs btn-link ax-cart-checkin"></button>')
				.text(__('Check-in slip'))
				.on('click', () => this._print_checkin(c))
				.appendTo($item);
		});
	}

	_cart_dots(c) {
		const is_emp = c.party_type === 'Employee';
		const housed = true;
		const custody = is_emp ? !!c._custody_issue : null;
		const card = is_emp ? !!c._card_done : null;
		const transport = !!this.transportStarted;
		const DOT_STYLE = { on: AX_STYLE.cart_dot_on, off: AX_STYLE.cart_dot_off, na: AX_STYLE.cart_dot_na };
		const dot = (label, state) => {
			const mark = state === null ? '–' : state ? '✓' : '–';
			const cls = state === null ? 'na' : state ? 'on' : 'off';
			return `<span class="ax-cart-dot ax-cart-dot--${cls}" style="${DOT_STYLE[cls]}">${frappe.utils.escape_html(label)} ${mark}</span>`;
		};
		const html =
			dot(__('Housed'), housed) +
			dot(__('Custody'), custody) +
			dot(__('Card'), card) +
			dot(__('Transport'), transport);
		const complete = housed && (custody !== false) && (card !== false) && transport;
		return { html, complete };
	}

	_render_deck() {
		this.$deck.empty();
		this._render_stages();
		if (!this.cart.length) return;
		if (this.catalog == null) this._load_catalog();
		const $cust = $('<section class="ax-deck-sec" data-stage-target="custody"></section>').attr('style', AX_STYLE.deck_sec).appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').attr('style', AX_STYLE.deck_head).text(__('Custody Handover')).appendTo($cust);
		if (this.catalogError) {
			const $err = $('<div class="ax-catalog-error"></div>').attr('style', AX_STYLE.catalog_error).appendTo($cust);
			$('<span></span>').text(__("Couldn't load custody store — retry")).appendTo($err);
			$('<button class="btn btn-xs btn-default ax-catalog-retry"></button>')
				.text(__('Retry'))
				.on('click', () => this._retry_catalog())
				.appendTo($err);
		}
		const $list = $('<div class="ax-deck-list"></div>').attr('style', AX_STYLE.deck_list).appendTo($cust);
		this.cart.forEach((c) => this._custody_row($list, c));
		const $card = $('<section class="ax-deck-sec" data-stage-target="card"></section>').attr('style', AX_STYLE.deck_sec).appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').attr('style', AX_STYLE.deck_head).text(__('Arrival Card')).appendTo($card);
		const $clist = $('<div class="ax-deck-list"></div>').attr('style', AX_STYLE.deck_list).appendTo($card);
		this.cart.forEach((c) => this._card_row($clist, c));
		const pendingQr = this.cart.filter((c) => c.party_type === 'Employee' && !c._card_done);
		if (pendingQr.length) {
			$('<button class="btn btn-sm btn-default ax-qr-all"></button>')
				.attr('style', AX_STYLE.qr_all)
				.text(__('Create QR for all ({0})', [pendingQr.length]))
				.on('click', () => this._issue_group_qr())
				.appendTo($card);
		}
		$('<button class="btn btn-sm btn-default ax-cards-all"></button>')
			.text(__('Print arrival cards ({0})', [this.cart.length]))
			.on('click', () => this._print_all_cards())
			.appendTo($card);
		this.$qrBlock = $('<div class="ax-qr-block"></div>').attr('style', AX_STYLE.qr_block).appendTo($card);
		this._render_qr_block();
		this._transport_section();
	}

	_load_catalog() {
		this.catalog = [];
		this.catalogError = false;
		if (!this.building) return;
		frappe
			.call({
				method: 'apex.habitat.api.custody_kiosk.get_kiosk_catalog',
				args: { building: this.building },
			})
			.then((r) => {
				this.catalog = (r.message && r.message.articles) || [];
				this.catalogError = false;
				if (this.cart.length) this._render_deck();
			})
			.catch(() => {
				this.catalog = [];
				this.catalogError = true;
				if (this.cart.length) this._render_deck();
			});
	}

	_retry_catalog() {
		this.catalog = null;
		this.catalogError = false;
		this._load_catalog();
	}

	_custody_row($list, c) {
		const $row = $('<div class="ax-deck-row"></div>').attr('style', AX_STYLE.deck_row).appendTo($list);
		$('<span class="ax-deck-name"></span>').attr('style', AX_STYLE.deck_name).text(c.label || c.party).appendTo($row);
		if (c.party_type === 'Temporary Worker') {
			$('<span class="indicator-pill no-indicator-dot orange"></span>')
				.text(__('Custody deferred'))
				.appendTo($row);
			return;
		}
		if (c._custody_issue) {
			$('<span class="indicator-pill no-indicator-dot green"></span>').text(__('Issued')).appendTo($row);
			$('<button class="btn btn-xs btn-link ax-deck-handover"></button>')
				.text(__('Print handover'))
				.on('click', () => this._print_custody(c))
				.appendTo($row);
			return;
		}
		$('<button class="btn btn-sm btn-default ax-deck-btn"></button>')
			.text(__('Issue custody'))
			.on('click', (e) => this._custody_cart($(e.currentTarget).closest('.ax-deck-row'), c))
			.appendTo($row);
	}

	_custody_cart($row, c) {
		if ($row.find('.ax-custody-cart').length) return;
		$row.find('.ax-deck-btn').remove();
		c._custody_lines = c._custody_lines || [];
		const $panel = $('<div class="ax-custody-cart"></div>').attr('style', AX_STYLE.custody_cart).appendTo($row);
		const $lines = $('<div class="ax-custody-lines"></div>').attr('style', AX_STYLE.custody_lines).appendTo($panel);
		const $add = $('<div class="ax-custody-add"></div>').attr('style', AX_STYLE.custody_add).appendTo($panel);
		const $foot = $('<div class="ax-custody-foot"></div>').attr('style', AX_STYLE.custody_foot).appendTo($panel);
		const $issue = $('<button class="btn btn-sm btn-primary"></button>').attr('style', AX_STYLE.custody_issue_btn).appendTo($foot);

		const $sel = $('<select class="form-control form-control-sm ax-custody-article"></select>').attr('style', AX_STYLE.custody_article).appendTo($add);
		$('<option value=""></option>').text(__('Article…')).appendTo($sel);
		(this.catalog || []).forEach((a) => {
			const bal = a.store_balance != null ? ` (${a.store_balance} ${a.uom || ''})` : '';
			$('<option></option>')
				.attr('value', a.article)
				.text(`${a.article_name || a.article}${bal}`)
				.appendTo($sel);
		});
		const $qty = $(
			'<input type="number" class="form-control form-control-sm ax-custody-qty" min="1" value="1" />'
		)
			.attr('style', AX_STYLE.custody_qty)
			.appendTo($add);

		const renderLines = () => {
			$lines.empty();
			c._custody_lines.forEach((l, i) => {
				const $li = $('<div class="ax-custody-line"></div>').attr('style', AX_STYLE.custody_line).appendTo($lines);
				$('<span></span>').text(`${l.qty} × ${l.label || l.article}`).appendTo($li);
				$('<button class="btn btn-xs btn-link text-danger"></button>')
					.text('×')
					.attr('title', __('Remove'))
					.on('click', () => {
						c._custody_lines.splice(i, 1);
						renderLines();
					})
					.appendTo($li);
			});
			$issue.text(__('Issue all ({0})', [c._custody_lines.length])).prop('disabled', !c._custody_lines.length);
		};

		$('<button class="btn btn-sm btn-default"></button>')
			.text(__('Add'))
			.on('click', () => {
				const art = $sel.val();
				const qty = parseInt($qty.val(), 10) || 1;
				if (!art) {
					frappe.show_alert({ message: __('Pick an article.'), indicator: 'orange' });
					return;
				}
				const label = $sel.find('option:selected').text();
				const existing = c._custody_lines.find((l) => l.article === art);
				if (existing) existing.qty += qty;
				else c._custody_lines.push({ article: art, label, qty });
				$sel.val('');
				$qty.val(1);
				renderLines();
			})
			.appendTo($add);

		$issue.on('click', () => {
			if (!c._custody_lines.length) return;
			frappe.call({
				method: 'apex.habitat.api.custody_kiosk.issue_cart',
				args: {
					employee: c.party,
					building: this.building,
					items_json: JSON.stringify(c._custody_lines.map((l) => ({ article: l.article, qty: l.qty }))),
				},
				freeze: true,
				freeze_message: __('Issuing custody…'),
				callback: (r) => {
					if (r.exc || !r.message) return;
					c._custody_issue = r.message.custody_issue;
					this.custodyIssued = true;
					frappe.show_alert({ message: __('Custody issued to {0}', [c.label]), indicator: 'green' });
					this._render_stages();
					this._load_catalog();
					this.refresh();
				},
			});
		});
		renderLines();
	}

	_card_row($list, c) {
		const $row = $('<div class="ax-deck-row"></div>').attr('style', AX_STYLE.deck_row).appendTo($list);
		$('<span class="ax-deck-name"></span>').attr('style', AX_STYLE.deck_name).text(c.label || c.party).appendTo($row);
		if (c.party_type === 'Employee') {
			if (c._card_done) {
				$('<span class="indicator-pill no-indicator-dot green"></span>').text(__('QR issued')).appendTo($row);
			}
		} else {
			$('<span class="indicator-pill no-indicator-dot orange"></span>')
				.text(__('Link after registration'))
				.appendTo($row);
		}
		$('<button class="btn btn-sm btn-default"></button>')
			.text(__('Print slip'))
			.on('click', () => this._print_slip(c))
			.appendTo($row);
	}

	_issue_group_qr() {
		const targets = this.cart.filter((c) => c.party_type === 'Employee' && !c._card_done);
		if (!targets.length) return;
		targets.forEach((c) => (c._card_pending = true));
		this._render_qr_block();
		frappe.call({
			method: 'apex.apex_core.doctype.masar_worker_token.masar_worker_token.batch_issue_worker_links',
			args: { employees_json: JSON.stringify(targets.map((c) => c.party)) },
			callback: (r) => {
				targets.forEach((c) => (c._card_pending = false));
				if (r.exc || !r.message) {
					this._render_qr_block();
					return;
				}
				(r.message || []).forEach((m) => {
					const c = this.cart.find((x) => x.party_type === 'Employee' && x.party === m.employee);
					if (c) {
						c._card_done = true;
						c._card_qr = m;
					}
				});
				this.cardIssued = true;
				frappe.show_alert({
					message: __('QR created for {0} worker(s)', [r.message.length]),
					indicator: 'green',
				});
				this._render_stages();
				this._render_deck();
			},
			error: () => {
				targets.forEach((c) => (c._card_pending = false));
				this._render_qr_block();
			},
		});
	}

	_render_qr_block() {
		this.$qrBlock.empty();
		this.cart
			.filter((c) => c._card_qr || c._card_pending)
			.forEach((c) => {
				const $item = $('<div class="ax-qr-item"></div>').attr('style', AX_STYLE.qr_item).appendTo(this.$qrBlock);
				$('<div class="ax-qr-name"></div>').attr('style', AX_STYLE.qr_name).text(c.label || c.party).appendTo($item);
				if (c._card_pending) {
					$('<div class="ax-qr-pending"></div>')
						.attr('style', AX_STYLE.qr_pending)
						.html(`<span class="ax-qr-spinner" aria-hidden="true" style="${AX_STYLE.qr_spinner}"></span>`)
						.append(document.createTextNode(__('Creating QR…')))
						.appendTo($item);
					return;
				}
				const m = c._card_qr;
				if (m.qr) $('<img class="ax-qr-img" alt="QR" />').attr('style', AX_STYLE.qr_img).attr('src', m.qr).appendTo($item);
				const $link = $('<a class="ax-qr-link" target="_blank" rel="noopener"></a>').attr('style', AX_STYLE.qr_link).attr('href', m.link);
				$('<bdi></bdi>').text(m.link).appendTo($link);
				$link.appendTo($item);
				if (m.phone) {
					$('<button class="btn btn-xs btn-default ax-qr-send"></button>')
						.text(__('Send via WhatsApp/SMS'))
						.on('click', (e) => this._send_masar_message(c, $(e.currentTarget)))
						.appendTo($item);
				}
			});
	}

	_send_masar_message(c, $btn) {
		const m = c._card_qr || {};
		$btn.prop('disabled', true).text(__('Sending…'));
		frappe.call({
			method: 'apex.habitat.api.arrivals_desk.send_masar_link_message',
			args: { employee: c.party, phone: m.phone || null },
			callback: (r) => {
				if (r.exc) {
					$btn.prop('disabled', false).text(__('Send via WhatsApp/SMS'));
					frappe.show_alert({
						message: __('Could not send the link. Please try again.'),
						indicator: 'red',
					});
					return;
				}
				const res = r.message || {};
				if (res.queued) {
					$btn.text(__('Sent ✓'));
					frappe.show_alert({ message: __('Link sent to {0}', [c.label || c.party]), indicator: 'green' });
				} else if (res.gateway_configured === false) {
					$btn.prop('disabled', false).text(__('Send via WhatsApp/SMS'));
					frappe.show_alert({
						message: __('Messaging gateway is not configured yet (Apex Integration Settings).'),
						indicator: 'orange',
					});
				} else {
					$btn.prop('disabled', false).text(__('Send via WhatsApp/SMS'));
					frappe.show_alert({ message: __('Could not send the link.'), indicator: 'red' });
				}
			},
			error: () => $btn.prop('disabled', false).text(__('Send via WhatsApp/SMS')),
		});
	}

	_open_print(title, html) {
		const w = window.open('', '_blank');
		if (!w) {
			frappe.show_alert({ message: __('Allow pop-ups to print the slip.'), indicator: 'orange' });
			return null;
		}
		w.document.write(
			`<html><head><title>${frappe.utils.escape_html(title || '')}</title></head>` +
				`<body onload="window.print()">${html}</body></html>`
		);
		w.document.close();
		return w;
	}

	_print_slip(c) {
		frappe.call({
			method: 'apex.habitat.api.arrivals_desk.get_arrival_slip',
			args: { party_type: c.party_type, party: c.party },
			callback: (r) => {
				if (r.exc || !r.message) return;
				this._open_print(r.message.title, r.message.html);
			},
		});
	}

	_print_checkin(c) {
		frappe.call({
			method: 'apex.habitat.api.arrivals_desk.get_checkin_slip',
			args: { party_type: c.party_type, party: c.party },
			callback: (r) => {
				if (r.exc || !r.message) return;
				this._open_print(r.message.title, r.message.html);
			},
		});
	}

	_print_custody(c) {
		if (!c._custody_issue) {
			frappe.show_alert({ message: __('Issue custody first'), indicator: 'orange' });
			return;
		}
		frappe.call({
			method: 'apex.habitat.api.arrivals_desk.get_custody_handover_slip',
			args: { custody_issue: c._custody_issue },
			callback: (r) => {
				if (r.exc || !r.message) return;
				this._open_print(r.message.title, r.message.html);
			},
		});
	}

	_print_all_cards() {
		if (!this.cart.length) return;
		const calls = this.cart.map((c) =>
			frappe.call({
				method: 'apex.habitat.api.arrivals_desk.get_arrival_slip',
				args: { party_type: c.party_type, party: c.party },
			})
		);
		frappe.dom.freeze(__('Building arrival cards…'));
		Promise.all(calls)
			.then((results) => {
				const html = (results || [])
					.filter((r) => r && r.message && r.message.html)
					.map((r) => r.message.html)
					.join('<div style="page-break-after:always"></div>');
				if (html) this._open_print(__('Arrival Cards'), html);
			})
			.catch(() => {})
			.then(() => frappe.dom.unfreeze());
	}

	_transport_section() {
		const $tr = $('<section class="ax-deck-sec" data-stage-target="transport"></section>').attr('style', AX_STYLE.deck_sec).appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').attr('style', AX_STYLE.deck_head).text(__('Transport')).appendTo($tr);
		const $tlist = $('<div class="ax-deck-list"></div>').attr('style', AX_STYLE.deck_list).appendTo($tr);
		const employees = this.cart.filter((c) => c.party_type === 'Employee');
		const tws = this.cart.filter((c) => c.party_type === 'Temporary Worker');
		employees.forEach((c) => {
			const $row = $('<label class="ax-deck-row ax-tr-row"></label>').attr('style', AX_STYLE.tr_row).appendTo($tlist);
			$('<input type="checkbox" checked />').attr('data-party', c.party).appendTo($row);
			$('<span class="ax-deck-name"></span>').attr('style', AX_STYLE.deck_name).text(c.label || c.party).appendTo($row);
		});
		tws.forEach((c) => {
			const $row = $('<div class="ax-deck-row"></div>').attr('style', AX_STYLE.deck_row).appendTo($tlist);
			$('<span class="ax-deck-name"></span>').attr('style', AX_STYLE.deck_name).text(c.label || c.party).appendTo($row);
			$('<span class="indicator-pill no-indicator-dot orange"></span>')
				.text(__('Unregistered manifest'))
				.appendTo($row);
		});
		if (employees.length) {
			$('<button class="btn btn-sm btn-default ax-tr-go"></button>')
				.attr('style', AX_STYLE.tr_go)
				.text(__('Create one transport request'))
				.on('click', () => this._create_transport($tlist))
				.appendTo($tr);
		} else if (tws.length) {
			$('<div class="ax-tr-note text-muted"></div>')
				.attr('style', AX_STYLE.tr_note)
				.text(__('Temporary workers board via the trip’s unregistered manifest.'))
				.appendTo($tr);
		}
	}

	/* The Transport stage is marked from the SAVE, not from the tap. `frappe.new_doc` only
	   opens a draft, so marking it beside that call told the clerk transport was arranged
	   for a form they might close without saving. */
	_watch_transport_saved() {
		frappe.ui.form.on('Transport Request', {
			after_save: (frm) => {
				if (!this.building || frm.doc.accommodation_building !== this.building) return;
				this.transportStarted = true;
				this._render_stages();
			},
		});
	}

	_create_transport($tlist) {
		const workers = [];
		$tlist.find('input[type="checkbox"]:checked').each((i, el) => {
			workers.push({ employee: $(el).attr('data-party') });
		});
		if (!workers.length) {
			frappe.show_alert({ message: __('Select at least one passenger.'), indicator: 'orange' });
			return;
		}
		frappe.new_doc('Transport Request', {
			service_line: 'Site Transport',
			request_type: 'Accommodation to Project Shuttle',
			project: this.project || undefined,
			accommodation_building: this.building || undefined,
			workers,
		});
	}

	_render_capacity(grid) {
		if (!grid) {
			this.$capacity.empty();
			return;
		}
		const s = grid.summary || {};
		const free = s.available || 0;
		const occupied = s.occupied || 0;
		const total = s.total_beds || 0;
		const over = Math.max(0, occupied - total);
		const physOcc = occupied - over;
		const denom = total + over || 1;
		const $cap = $('<div class="ax-cap-wrap"></div>').attr('style', AX_STYLE.cap_wrap);
		$('<span class="ax-cap-title"></span>').attr('style', AX_STYLE.cap_title).text(grid.building_title || '').appendTo($cap);
		const $meter = $(
			`<div class="ax-cap-meter" role="img" ` +
				`aria-label="${__('{0} free of {1} beds', [free, total])}" ` +
				`title="${__('{0} free of {1} beds', [free, total])}"></div>`
		)
			.attr('style', AX_STYLE.cap_meter)
			.appendTo($cap);
		$('<div class="ax-cap-fill ax-cap-fill--free"></div>')
			.attr('style', AX_STYLE.cap_fill + AX_STYLE.cap_fill_free)
			.css('width', `${Math.round((free / denom) * 100)}%`)
			.appendTo($meter);
		$('<div class="ax-cap-fill ax-cap-fill--occ"></div>')
			.attr('style', AX_STYLE.cap_fill + AX_STYLE.cap_fill_occ)
			.css('width', `${Math.round((physOcc / denom) * 100)}%`)
			.appendTo($meter);
		if (over) {
			$('<div class="ax-cap-fill ax-cap-fill--over"></div>')
				.attr('style', AX_STYLE.cap_fill + AX_STYLE.cap_fill_over)
				.css('width', `${Math.round((over / denom) * 100)}%`)
				.appendTo($meter);
		}
		const legend = (variant, swatch, label) => {
			const $l = $(`<div class="ax-cap-legend ax-cap-legend--${variant}"></div>`)
				.attr('style', AX_STYLE.cap_legend)
				.appendTo($cap);
			$('<span></span>').attr('style', AX_STYLE.cap_swatch + `background:${swatch};`).appendTo($l);
			$('<span></span>').text(label).appendTo($l);
		};
		legend('free', 'var(--green-500)', __('{0} free', [free]));
		legend('occ', 'var(--red-500)', __('{0} occupied', [occupied]));
		if (over) legend('over', 'var(--orange-500)', __('{0} over capacity', [over]));
		this.$capacity.empty().append($cap);
	}

	_render_stages() {
		const housed = this.cart.length > 0;
		const chips = [
			['building', __('Building'), !!this.building],
			['housed', __('Housed'), housed],
			['custody', __('Custody'), this.custodyIssued],
			['card', __('Card'), this.cardIssued],
			['transport', __('Transport'), this.transportStarted],
		];
		const firstTodo = chips.findIndex(([, , done]) => !done);
		this.$stages.empty().attr('role', 'list');
		chips.forEach(([k, label, done], i) => {
			const state = done ? 'done' : i === firstTodo ? 'now' : 'todo';
			const $step = $(
				`<button type="button" class="ax-step ax-step--${state}" data-stage="${k}" role="listitem"></button>`
			).attr('style', AX_STEP.base + AX_STEP[state]);
			$('<span class="ax-step-num"></span>')
				.attr('style', AX_STEP_NUM.base + AX_STEP_NUM[state])
				.text(i + 1)
				.appendTo($step);
			$('<span class="ax-step-label"></span>').text(label).appendTo($step);
			if (done) {
				$step.on('click', () => this._scroll_to_stage(k));
			} else {
				$step.prop('disabled', true);
			}
			this.$stages.append($step);
		});
	}

	_scroll_to_stage(stage) {
		const el = this.$deck && this.$deck.find(`[data-stage-target="${stage}"]`).get(0);
		if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
	}

	_render_grid(grid) {
		this._render_capacity(grid);
		this._render_stages();
		const summary = (grid && grid.summary) || {};
		if (!grid || !(grid.floors || []).length) {
			const msg =
				summary.total_beds > 0
					? __('This building has rooms but every bed is occupied — use Over-capacity')
					: __('This building has no rooms yet.');
			this._render_empty(msg);
			return;
		}
		this.$floor.html(
			grid.floors
				.map((floor) => {
					const rooms = (floor.rooms || []).map((room) => this._room_html(room)).join('');
					return (
						`<section class="ax-floor-group" style="${AX_STYLE.floor_group}"><header class="ax-floor-header" style="${AX_STYLE.floor_header}">` +
						`${frappe.utils.escape_html(floor.floor_label || '')}</header>` +
						`<div class="ax-rooms" style="${AX_STYLE.rooms}">${rooms}</div></section>`
					);
				})
				.join('')
		);
		if (summary.total_beds > 0 && !summary.available) {
			$('<div class="ax-floor-banner"></div>')
				.attr('style', AX_STYLE.floor_banner)
				.text(__('This building has rooms but every bed is occupied — use Over-capacity'))
				.prependTo(this.$floor);
		}
	}

	_room_html(room) {
		const beds = (room.beds || []).map((bed) => this._bed_html(bed, room.readiness_status)).join('');
		const occ = `${room.current_occupancy || 0}/${room.bed_capacity || 0}`;
		const sameProject = !!(this.project && room.dominant_project && room.dominant_project === this.project);
		const projClass = sameProject ? ' ax-room--same-project' : '';
		const roomStyle = AX_STYLE.room + (sameProject ? AX_STYLE.room_same_project : '');
		const projBadge = sameProject
			? `<span class="ax-room-proj" style="${AX_STYLE.room_proj}" title="${__('Same project as the selected worker')}">${__('Same project')}</span>`
			: '';
		const readiness =
			room.readiness_status && room.readiness_status !== 'Ready' && room.readiness_status !== 'Unknown'
				? ` · ${frappe.utils.escape_html(__(room.readiness_status))}`
				: '';
		const has_free = (room.beds || []).some((b) => b.bed_color === 'green');
		const oc = has_free
			? ''
			: `<button class="ax-room-oc" style="${AX_STYLE.room_oc}" data-room="${frappe.utils.escape_html(room.room || '')}" ` +
			  `title="${__('House over capacity in a temporary bed')}">+ ${__('Over-capacity')}</button>`;
		return (
			`<div class="ax-room${projClass}" style="${roomStyle}"><div class="ax-room-header" style="${AX_STYLE.room_header}">` +
			`<span class="ax-room-number" style="${AX_STYLE.room_number}">${frappe.utils.escape_html(room.room_number || room.room || '')}${projBadge}</span>` +
			`<span class="ax-room-meta" style="${AX_STYLE.room_meta}">${occ}${readiness}</span></div>` +
			`<div class="ax-beds" style="${AX_STYLE.beds}">${beds}</div>${oc}</div>`
		);
	}

	_bed_html(bed, readiness_status) {
		const color = bed.bed_color || 'grey';
		const temp = bed.is_temporary ? ' ax-bed--temp' : '';
		const a11y = color === 'green' || color === 'red' ? ' tabindex="0" role="button"' : '';
		const name = bed.occupant ? bed.occupant.employee_name || bed.occupant.employee || '' : '';
		const occupant = bed.occupant
			? `<span class="ax-bed-occupant" style="${AX_STYLE.bed_occupant}" title="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(
					name
			  )}</span>`
			: '';
		const custody =
			bed.occupant && bed.occupant.has_custody
				? `<span class="ax-bed-badge" style="${AX_STYLE.bed_badge}" title="${__('Has custody')}">●</span>`
				: '';
		const blocker =
			color === 'amber' && readiness_status && readiness_status !== 'Ready' && readiness_status !== 'Unknown'
				? `<span class="ax-bed-blocker" style="${AX_STYLE.bed_blocker}">${frappe.utils.escape_html(__(readiness_status))}</span>`
				: '';
		const tempChip = bed.is_temporary
			? `<span class="ax-bed-chip ax-bed-chip--temp" style="${AX_STYLE.bed_chip + AX_STYLE.bed_chip_temp}">${__('Temp')}</span>`
			: '';
		const bedStyle = ax_bed_style(color, { temp: !!bed.is_temporary });
		return (
			`<div class="ax-bed ax-bed--${color}${temp}" style="${bedStyle}" data-bed="${frappe.utils.escape_html(bed.bed || '')}"${a11y} ` +
			`title="${frappe.utils.escape_html(bed.bed_code || '')}">` +
			`<span class="ax-bed-code" style="${AX_STYLE.bed_code}"><bdi>${frappe.utils.escape_html(bed.bed_code || '')}</bdi>${tempChip}</span>` +
			`${occupant}${blocker}${custody}</div>`
		);
	}

	_render_empty(msg) {
		this.$floor.html(`<div class="ax-empty" style="${AX_STYLE.empty}">${frappe.utils.escape_html(msg)}</div>`);
	}

	_render_loading() {
		this.$floor.html(
			`<div class="ax-skeleton" style="${AX_STYLE.skeleton}">${`<div class="ax-skeleton-room" style="${AX_STYLE.skeleton_room}"></div>`.repeat(
				6
			)}</div>`
		);
	}

	_render_error() {
		this.$floor.html(
			`<div class="ax-error" style="${AX_STYLE.empty}"><div class="ax-error-msg" style="${AX_STYLE.error_msg}">` +
				`${__('Could not load the building. Please retry.')}</div>` +
				`<button class="btn btn-default btn-sm ax-retry">${__('Retry')}</button></div>`
		);
		this.$floor.find('.ax-retry').on('click', () => this.refresh());
	}
}
