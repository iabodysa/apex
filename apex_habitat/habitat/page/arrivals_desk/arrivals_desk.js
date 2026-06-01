// Arrivals Desk — "Anchor / Floor / Cart" single-screen worker check-in.
//
// Building-first desk: pick a building (Zone A) → a read-only rooms/beds floor-map
// (Zone C) appears beside a worker rail. Search or register an arrival (Zone D /
// the one passport modal), pick a free bed to house him (party-aware), and the
// arrivals cart (Zone E) remembers everyone housed this session for the later
// custody / card / transport stages. Frappe desk library only; the AFMCO brand
// lives in the scoped arrivals_desk.css.
//
// Server is the source of truth: the floor-map reuses front_desk.get_building_grid
// (server-computed bed colour) and housing reuses front_desk.quick_check_in. After
// every write we RE-FETCH the grid rather than mutating tiles optimistically.

frappe.pages['arrivals-desk'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Arrivals Desk'),
		single_column: true,
	});
	wrapper.arrivals_desk = new ArrivalsDesk(page);
};

class ArrivalsDesk {
	constructor(page) {
		this.page = page;
		this.building = null;
		this.project = null;
		this.grid = null;
		this.active = null; // the worker currently being processed (party_type + party)
		this.cart = []; // workers housed in this arrival session (Zone E)
		this.custodyIssued = false; // any custody handed over this session (Zone F)
		this.cardIssued = false; // any Masar arrival link issued this session (Zone F)
		this._build_skeleton();
		this._setup_anchor();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		this._render_empty(__('Pick a building to start the arrival.'));
	}

	_build_skeleton() {
		this.$root = $('<div class="arrivals-desk"></div>').appendTo(this.page.main);
		// Frozen header: Zone A capacity readout + Zone B stage strip.
		this.$head = $('<div class="ax-head"></div>').appendTo(this.$root);
		this.$capacity = $('<div class="ax-capacity"></div>').appendTo(this.$head);
		this.$stages = $('<div class="ax-stages"></div>').appendTo(this.$head);
		this._render_stages();
		// Body: floor-map (left) + worker rail (right).
		this.$body = $('<div class="ax-body"></div>').appendTo(this.$root);
		this.$floor = $('<div class="ax-floor"></div>').appendTo(this.$body);
		// Delegated: a click on a FREE bed houses the active worker (Batch 3); the
		// per-room over-capacity button mints a temporary bed (Batch 3b).
		this.$floor.on('click', '.ax-bed', (e) => this._on_bed_click(e));
		this.$floor.on('click', '.ax-room-oc', (e) => {
			e.stopPropagation();
			this._house_over_capacity($(e.currentTarget).attr('data-room'));
		});
		this.$rail = $('<aside class="ax-rail"></aside>').appendTo(this.$body);
		this._build_rail();
	}

	_setup_anchor() {
		this.building_field = this.page.add_field({
			fieldname: 'building',
			label: __('Building'),
			fieldtype: 'Link',
			options: 'Accommodation Building',
			change: () => {
				const val = this.building_field.get_value();
				if (val && val !== this.building) {
					this.building = val;
					this.refresh();
				} else if (!val && this.building) {
					this.building = null;
					this.grid = null;
					this._render_stages();
					this._render_capacity(null);
					this._render_empty(__('Pick a building to start the arrival.'));
				}
			},
		});
		// Second anchor: the session project. House actions stamp this project, so
		// the supervisor sets it once for the batch of arrivals (low friction).
		this.project_field = this.page.add_field({
			fieldname: 'project',
			label: __('Project'),
			fieldtype: 'Link',
			options: 'Project',
			change: () => {
				this.project = this.project_field.get_value() || null;
			},
		});
	}

	refresh() {
		if (!this.building) return;
		const requested = this.building;
		this._render_loading();
		frappe
			.call({
				method: 'apex_habitat.habitat.api.front_desk.get_building_grid',
				args: { building: this.building },
			})
			.then((r) => {
				if (this.building !== requested) return; // stale: a newer building was picked
				this.grid = r.message;
				this._render_grid(this.grid);
			})
			.catch(() => {
				if (this.building !== requested) return;
				this._render_error();
			});
	}

	// ---------- rail: worker search + the one passport modal (Batch 2) ----------
	_build_rail() {
		this.$rail.empty();
		const $search = $('<div class="ax-search"></div>').appendTo(this.$rail);
		this.$search_input = $(
			`<input type="search" class="ax-search-input form-control" placeholder="${__(
				'Search worker name or passport…'
			)}" />`
		).appendTo($search);
		this.$results = $('<div class="ax-results"></div>').appendTo($search);
		this.$active = $('<div class="ax-active"></div>').appendTo(this.$rail);
		this.$cart = $('<div class="ax-cart"></div>').appendTo(this.$rail);
		this.$deck = $('<div class="ax-deck"></div>').appendTo(this.$rail); // stage deck (Zone F)
		this.$search_input.on('input', frappe.utils.debounce(() => this._search(), 250));
		this._render_results(null);
		this._render_cart();
	}

	_search() {
		const txt = (this.$search_input.val() || '').trim();
		frappe
			.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.search_arrivals_workers',
				args: { building: this.building, txt },
			})
			.then((r) => this._render_results(r.message || []))
			.catch(() => this._render_results([]));
	}

	_render_results(rows) {
		this.$results.empty();
		if (rows && !rows.length) {
			$('<div class="ax-results-empty text-muted"></div>')
				.text(__('No registered workers match. Register a new arrival below.'))
				.appendTo(this.$results);
		} else if (rows) {
			rows.forEach((row) => this._result_row(row));
		}
		// "Register by passport" is always pinned at the BOTTOM (the page's only modal).
		$('<button class="btn btn-default btn-sm ax-register-row"></button>')
			.html(`<span class="ax-register-plus">+</span> ${__('Register new arrival by passport')}`)
			.on('click', () => this._open_register_modal())
			.appendTo(this.$results);
	}

	_result_row(row) {
		const is_tw = row.party_type === 'Temporary Worker';
		const $row = $(
			`<div class="ax-result" tabindex="0" role="button">` +
				`<span class="ax-result-badge ax-result-badge--${is_tw ? 'tw' : 'emp'}">${
					is_tw ? __('Temp') : __('Emp')
				}</span>` +
				`<span class="ax-result-label">${frappe.utils.escape_html(row.label || '')}</span>` +
				`<span class="ax-result-sub text-muted">${frappe.utils.escape_html(row.sub || '')}</span></div>`
		).appendTo(this.$results);
		const pick = () => {
			this.$results.find('.ax-result').removeClass('ax-result--active');
			$row.addClass('ax-result--active');
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
		this.$active.html(`<div class="ax-active-card ax-active-card--load text-muted">${__('Loading…')}</div>`);
		frappe
			.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.get_arrival_card',
				args: { party_type: row.party_type, party: row.party },
			})
			.then((r) => this._render_active_card(r.message))
			.catch(() =>
				this.$active.html(`<div class="ax-active-card text-muted">${__('Could not load the worker.')}</div>`)
			);
	}

	_render_active_card(card) {
		if (!card) {
			this.$active.empty();
			return;
		}
		const is_tw = card.party_type === 'Temporary Worker';
		const bed = card.current_bed_code || card.current_bed || '';
		const foot = card.has_housing
			? `<span class="ax-active-bed">${__('Bed')}: ${frappe.utils.escape_html(bed)}</span>`
			: `<span class="ax-active-hint">${__('Click a free bed to house him.')}</span>`;
		this.$active.html(
			`<div class="ax-active-card"><div class="ax-active-head">` +
				`<span class="ax-active-name">${frappe.utils.escape_html(card.worker_name || card.party)}</span>` +
				`<span class="ax-result-badge ax-result-badge--${is_tw ? 'tw' : 'emp'}">${
					is_tw ? __('Temporary Worker') : __('Employee')
				}</span></div>` +
				`<div class="ax-active-sub text-muted">${
					card.project ? frappe.utils.escape_html(card.project) : __('No project yet')
				}</div>` +
				`<div class="ax-active-foot">${foot}</div></div>`
		);
	}

	_open_register_modal() {
		const d = new frappe.ui.Dialog({
			title: __('Register New Arrival (Passport)'),
			fields: [
				{ fieldname: 'worker_name', label: __('Worker Name'), fieldtype: 'Data', reqd: 1 },
				{ fieldname: 'passport_number', label: __('Passport Number'), fieldtype: 'Data', reqd: 1 },
				{ fieldname: 'cb1', fieldtype: 'Column Break' },
				{ fieldname: 'nationality', label: __('Nationality'), fieldtype: 'Data' },
				{ fieldname: 'labour_supplier', label: __('Labour Supplier'), fieldtype: 'Data' },
				{ fieldname: 'sb1', fieldtype: 'Section Break' },
				{
					fieldname: 'building',
					label: __('Building'),
					fieldtype: 'Link',
					options: 'Accommodation Building',
					default: this.building,
				},
				{
					fieldname: 'project',
					label: __('Project'),
					fieldtype: 'Link',
					options: 'Project',
					default: this.project,
				},
				{ fieldname: 'cb2', fieldtype: 'Column Break' },
				{ fieldname: 'cell_number', label: __('Cell Number'), fieldtype: 'Data' },
				{ fieldname: 'iqama_number', label: __('Iqama Number (if any)'), fieldtype: 'Data' },
			],
			primary_action_label: __('Register'),
			primary_action: (values) => {
				frappe.call({
					method: 'apex_habitat.habitat.api.arrivals_desk.register_temporary_worker',
					args: values,
					freeze: true,
					freeze_message: __('Registering…'),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						frappe.show_alert({ message: __('Registered: {0}', [r.message.label]), indicator: 'green' });
						this._select_worker(r.message); // make the new arrival active
						this._search(); // refresh the result list
					},
				});
			},
		});
		d.show();
	}

	// ---------- assign interaction + arrivals cart (Batch 3) ----------
	_on_bed_click(e) {
		const $bed = $(e.currentTarget);
		if (!$bed.hasClass('ax-bed--green')) return; // only free beds house (over-capacity is a later step)
		if (!this.active) {
			frappe.show_alert({ message: __('Pick a worker first.'), indicator: 'orange' });
			return;
		}
		if (!this.project) {
			frappe.show_alert({ message: __('Pick a project first.'), indicator: 'orange' });
			return;
		}
		this._house_in_bed($bed.attr('data-bed'));
	}

	_house_in_bed(bed) {
		const worker = this.active;
		frappe.call({
			method: 'apex_habitat.habitat.api.front_desk.quick_check_in',
			args: {
				bed,
				party_type: worker.party_type,
				party: worker.party,
				project: this.project,
				check_in_date: frappe.datetime.get_today(),
			},
			freeze: true,
			freeze_message: __('Housing…'),
			callback: (r) => {
				if (r.exc || !r.message) return;
				frappe.show_alert({ message: __('Housed {0}', [worker.label]), indicator: 'green' });
				// Remember in the session cart (dedupe by party) for the later stages.
				const dupe = this.cart.some(
					(c) => c.party === worker.party && c.party_type === worker.party_type
				);
				if (!dupe) this.cart.push({ ...worker, bed: r.message.bed || bed });
				this.active = null;
				this.$active.empty();
				this._render_cart();
				this.refresh(); // re-fetch the grid → the bed turns red, counts + stages update
			},
		});
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
		// Over-capacity is consequential, so confirm first — a guardrail, not a data
		// form, so the page still has exactly one data modal (the passport register).
		frappe.confirm(__('Room is full. House {0} in a temporary over-capacity bed?', [worker.label]), () => {
			frappe.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.house_over_capacity',
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
					this.active = null;
					this.$active.empty();
					this._render_cart();
					this.refresh();
				},
			});
		});
	}

	_render_cart() {
		this._render_deck(); // the stage deck depends on the cart; refresh it alongside
		this.$cart.empty();
		if (!this.cart.length) return;
		$('<div class="ax-cart-title"></div>')
			.text(__('Arrived this session ({0})', [this.cart.length]))
			.appendTo(this.$cart);
		const $list = $('<div class="ax-cart-list"></div>').appendTo(this.$cart);
		this.cart.forEach((c) => {
			$('<div class="ax-cart-item"></div>')
				.html(
					`<span class="ax-cart-name">${frappe.utils.escape_html(c.label || c.party)}</span>` +
						`<span class="ax-cart-bed text-muted">${frappe.utils.escape_html(c.bed || '')}</span>`
				)
				.appendTo($list);
		});
	}

	// ---------- stage deck: custody handover (Batch 4) ----------
	_render_deck() {
		this.$deck.empty();
		if (!this.cart.length) return;
		if (!this.articles) this._load_articles();
		const $cust = $('<section class="ax-deck-sec"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Custody Handover')).appendTo($cust);
		const $list = $('<div class="ax-deck-list"></div>').appendTo($cust);
		this.cart.forEach((c) => this._custody_row($list, c));
		// Arrival Card (Zone F): Masar link (Employee) + on-demand print slip (all).
		const $card = $('<section class="ax-deck-sec"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Arrival Card')).appendTo($card);
		const $clist = $('<div class="ax-deck-list"></div>').appendTo($card);
		this.cart.forEach((c) => this._card_row($clist, c));
	}

	_load_articles() {
		this.articles = []; // mark as loading to avoid repeat fetches
		frappe.db
			.get_list('Custody Article', { fields: ['name'], limit: 200, order_by: 'name asc' })
			.then((rows) => {
				this.articles = rows.map((r) => r.name);
			})
			.catch(() => {
				this.articles = [];
			});
	}

	_custody_row($list, c) {
		const $row = $('<div class="ax-deck-row"></div>').appendTo($list);
		$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
		if (c.party_type === 'Temporary Worker') {
			// TW custody is deferred until the Iqama links the Employee (no stock posting now).
			$('<span class="ax-deferred"></span>').text(__('Custody deferred')).appendTo($row);
			return;
		}
		if (c._custody_done) {
			$('<span class="ax-deck-ok"></span>').text(__('Issued')).appendTo($row);
			return;
		}
		$('<button class="btn btn-xs btn-default ax-deck-btn"></button>')
			.text(__('Issue custody'))
			.on('click', (e) => this._custody_inline($(e.currentTarget).closest('.ax-deck-row'), c))
			.appendTo($row);
	}

	_custody_inline($row, c) {
		if ($row.find('.ax-custody-form').length) return; // already open
		$row.find('.ax-deck-btn').remove();
		const $form = $('<div class="ax-custody-form"></div>').appendTo($row);
		const $sel = $('<select class="form-control input-xs ax-custody-article"></select>').appendTo($form);
		$('<option value=""></option>').text(__('Article…')).appendTo($sel);
		(this.articles || []).forEach((a) => $('<option></option>').attr('value', a).text(a).appendTo($sel));
		const $qty = $('<input type="number" class="form-control input-xs ax-custody-qty" min="1" value="1" />').appendTo(
			$form
		);
		$('<button class="btn btn-xs btn-primary"></button>')
			.text(__('Issue'))
			.on('click', () => {
				const art = $sel.val();
				const qty = parseInt($qty.val(), 10) || 1;
				if (!art) {
					frappe.show_alert({ message: __('Pick an article.'), indicator: 'orange' });
					return;
				}
				frappe.call({
					method: 'apex_habitat.habitat.api.custody_kiosk.issue_cart',
					args: {
						employee: c.party, // an Employee party — issue_cart posts to his ledger
						building: this.building,
						items_json: JSON.stringify([{ article: art, qty }]),
					},
					freeze: true,
					freeze_message: __('Issuing custody…'),
					callback: (r) => {
						if (r.exc || !r.message) return;
						c._custody_done = true;
						this.custodyIssued = true;
						frappe.show_alert({ message: __('Custody issued to {0}', [c.label]), indicator: 'green' });
						this._render_stages();
						this._render_deck();
					},
				});
			})
			.appendTo($form);
	}

	_card_row($list, c) {
		const $row = $('<div class="ax-deck-row"></div>').appendTo($list);
		$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
		if (c.party_type === 'Employee') {
			$('<button class="btn btn-xs btn-default"></button>')
				.text(c._card_done ? __('Link issued') : __('Masar link'))
				.on('click', () => this._issue_masar(c))
				.appendTo($row);
		} else {
			// A Temporary Worker's Masar link issues once he is registered as an Employee.
			$('<span class="ax-deferred"></span>').text(__('Link after registration')).appendTo($row);
		}
		$('<button class="btn btn-xs btn-default"></button>')
			.text(__('Print slip'))
			.on('click', () => this._print_slip(c))
			.appendTo($row);
	}

	_issue_masar(c) {
		frappe.call({
			method: 'apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.issue_worker_link',
			args: { employee: c.party, regenerate: 0 },
			freeze: true,
			freeze_message: __('Issuing worker link…'),
			callback: (r) => {
				if (r.exc || !r.message) return;
				c._card_done = true;
				this.cardIssued = true;
				// Shared helper from public/js/masar_worker_link.bundle.js (app_include_js).
				apex_habitat.masar.show_worker_link_dialog(r.message, { copy_link: true });
				this._render_stages();
				this._render_deck();
			},
		});
	}

	_print_slip(c) {
		frappe.call({
			method: 'apex_habitat.habitat.api.arrivals_desk.get_arrival_slip',
			args: { party_type: c.party_type, party: c.party },
			callback: (r) => {
				if (r.exc || !r.message) return;
				const w = window.open('', '_blank');
				if (!w) {
					frappe.show_alert({ message: __('Allow pop-ups to print the slip.'), indicator: 'orange' });
					return;
				}
				w.document.write(
					`<html><head><title>${frappe.utils.escape_html(r.message.title || '')}</title></head>` +
						`<body onload="window.print()">${r.message.html}</body></html>`
				);
				w.document.close();
			},
		});
	}

	// ---------- render ----------
	_render_capacity(grid) {
		if (!grid) {
			this.$capacity.empty();
			return;
		}
		const s = grid.summary || {};
		this.$capacity.html(
			`<span class="ax-cap-title">${frappe.utils.escape_html(grid.building_title || '')}</span>` +
				`<span class="ax-cap-counts"><b>${s.available || 0}</b> ${__('free')} · ` +
				`${s.occupied || 0} ${__('occupied')} · ${s.total_beds || 0} ${__('beds')}</span>`
		);
	}

	_render_stages() {
		const housed = this.cart.length > 0;
		const chips = [
			['building', __('Building'), !!this.building],
			['housed', __('Housed'), housed],
			['custody', __('Custody'), this.custodyIssued],
			['card', __('Card'), this.cardIssued],
			['transport', __('Transport'), false],
		];
		this.$stages.html(
			chips
				.map(
					([k, label, done]) =>
						`<span class="ax-stage ax-stage--${done ? 'done' : 'todo'}" data-stage="${k}">` +
						`${frappe.utils.escape_html(label)}</span>`
				)
				.join('')
		);
	}

	_render_grid(grid) {
		this._render_capacity(grid);
		this._render_stages();
		if (!grid || !(grid.floors || []).length) {
			this._render_empty(__('This building has no rooms or beds yet.'));
			return;
		}
		this.$floor.html(
			grid.floors
				.map((floor) => {
					const rooms = (floor.rooms || []).map((room) => this._room_html(room)).join('');
					return (
						`<section class="ax-floor-group"><header class="ax-floor-header">` +
						`${frappe.utils.escape_html(floor.floor_label || '')}</header>` +
						`<div class="ax-rooms">${rooms}</div></section>`
					);
				})
				.join('')
		);
	}

	_room_html(room) {
		const beds = (room.beds || []).map((bed) => this._bed_html(bed)).join('');
		const occ = `${room.current_occupancy || 0}/${room.bed_capacity || 0}`;
		const readiness =
			room.readiness_status && room.readiness_status !== 'Ready'
				? ` · ${frappe.utils.escape_html(room.readiness_status)}`
				: '';
		// No free bed → offer over-capacity housing (a temporary bed within the
		// building's overload headroom; the assignment enforces the cap).
		const has_free = (room.beds || []).some((b) => b.bed_color === 'green');
		const oc = has_free
			? ''
			: `<button class="ax-room-oc" data-room="${frappe.utils.escape_html(room.room || '')}" ` +
			  `title="${__('House over capacity in a temporary bed')}">+ ${__('Over-capacity')}</button>`;
		return (
			`<div class="ax-room"><div class="ax-room-header">` +
			`<span class="ax-room-number">${frappe.utils.escape_html(room.room_number || room.room || '')}</span>` +
			`<span class="ax-room-meta">${occ}${readiness}</span></div>` +
			`<div class="ax-beds">${beds}</div>${oc}</div>`
		);
	}

	_bed_html(bed) {
		const color = bed.bed_color || 'grey';
		const temp = bed.is_temporary ? ' ax-bed--temp' : ''; // virtual over-capacity bed
		const occupant = bed.occupant
			? `<span class="ax-bed-occupant">${frappe.utils.escape_html(
					bed.occupant.employee_name || bed.occupant.employee || ''
			  )}</span>`
			: '';
		const custody =
			bed.occupant && bed.occupant.has_custody
				? `<span class="ax-bed-badge" title="${__('Has custody')}">●</span>`
				: '';
		return (
			`<div class="ax-bed ax-bed--${color}${temp}" data-bed="${frappe.utils.escape_html(bed.bed || '')}" ` +
			`title="${frappe.utils.escape_html(bed.bed_code || '')}">` +
			`<span class="ax-bed-code">${frappe.utils.escape_html(bed.bed_code || '')}</span>` +
			`${occupant}${custody}</div>`
		);
	}

	_render_empty(msg) {
		this.$floor.html(`<div class="ax-empty">${frappe.utils.escape_html(msg)}</div>`);
	}

	_render_loading() {
		this.$floor.html(`<div class="ax-skeleton">${'<div class="ax-skeleton-room"></div>'.repeat(6)}</div>`);
	}

	_render_error() {
		this.$floor.html(
			`<div class="ax-error"><div class="ax-error-msg">` +
				`${__('Could not load the building. Please retry.')}</div>` +
				`<button class="btn btn-default btn-sm ax-retry">${__('Retry')}</button></div>`
		);
		this.$floor.find('.ax-retry').on('click', () => this.refresh());
	}
}
