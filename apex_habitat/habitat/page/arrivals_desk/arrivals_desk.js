// [#7ffkxk]

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
		this.cart = []; // workers housed in this arrival session (right zone)
		this.custodyIssued = false; // any custody handed over this session
		this.cardIssued = false; // any Masar arrival link issued this session
		this.transportStarted = false; // a transport request was created this session
		// [#frsjh3]
		this.page.hide_form();
		this._build_skeleton();
		this._setup_anchor();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		this._render_empty(__('Pick a building to start the arrival.'));
	}

	_build_skeleton() {
		this.$root = $('<div class="arrivals-desk"></div>').appendTo(this.page.main);
		// [#b5ku2i]
		this.$body = $('<div class="ax-body"></div>').appendTo(this.$root);

		// [#nzjhbw]
		this.$intake = $('<aside class="ax-zone ax-zone-intake"></aside>').appendTo(this.$body);

		// [#awqamr]
		this.$floorZone = $('<section class="ax-zone ax-zone-floor"></section>').appendTo(this.$body);
		this.$anchor = $('<div class="ax-anchor"></div>').appendTo(this.$floorZone);
		this.$capacity = $('<div class="ax-capacity"></div>').appendTo(this.$anchor);
		this.$stages = $('<div class="ax-stages"></div>').appendTo(this.$anchor); // 5-stage progress pills
		this.$floor = $('<div class="ax-floor"></div>').appendTo(this.$floorZone);
		// [#8gi0rj]
		this.$floor.on('click', '.ax-bed', (e) => this._on_bed_click(e));
		this.$floor.on('click', '.ax-room-oc', (e) => {
			e.stopPropagation();
			this._house_over_capacity($(e.currentTarget).attr('data-room'));
		});
		// [#r0hc0o]
		this.$floor.on('keydown', '.ax-bed--green', (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				this._on_bed_click(e);
			}
		});

		// [#mo583e]
		this.$actions = $('<aside class="ax-zone ax-zone-actions"></aside>').appendTo(this.$body);

		this._build_intake();
	}

	_setup_anchor() {
		// [#r86sw8]
		const $bWrap = $('<div class="ax-anchor-field"></div>').prependTo(this.$anchor);
		const $pWrap = $('<div class="ax-anchor-field"></div>').insertAfter($bWrap);

		this.building_field = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				fieldname: 'building',
				options: 'Accommodation Building',
				label: __('Building'),
				placeholder: __('Pick a building…'),
				onchange: () => this._on_building_change(),
			},
			parent: $bWrap.get(0),
			render_input: true,
		});
		this.building_field.refresh();

		// [#401r0k]
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

		// [#omdu8q]
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
			this.catalog = null; // reload the custody catalog for the new building's store
			this.refresh();
			this._load_catalog();
		} else if (!val && this.building) {
			// [#df9hzt]
			this.building = null;
			this.grid = null;
			this.catalog = null;
			this._render_stages();
			this._render_capacity(null);
			this._render_empty(__('Pick a building to start the arrival.'));
		}
	}

	_on_project_change() {
		this.project = this.project_field.get_value() || null;
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

	// [#3005gs]
	_build_intake() {
		this.$intake.empty();
		const $search = $('<div class="ax-search"></div>').appendTo(this.$intake);
		this.$search_input = $(
			`<input type="search" class="ax-search-input form-control form-control-sm" placeholder="${__(
				'Search worker name or passport…'
			)}" />`
		).appendTo($search);
		this.$results = $('<div class="ax-results"></div>').appendTo($search);
		this.$active = $('<div class="ax-active"></div>').appendTo(this.$intake);
		this.$cart = $('<div class="ax-cart"></div>').appendTo(this.$actions);
		this.$deck = $('<div class="ax-deck"></div>').appendTo(this.$actions); // stage deck
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
		// [#2tv16z]
		$('<button class="btn btn-default btn-sm ax-register-row"></button>')
			.html(`<span class="ax-register-plus">+</span> ${__('Register new arrival by passport')}`)
			.on('click', () => this._open_register_modal())
			.appendTo(this.$results);
	}

	_result_row(row) {
		const is_tw = row.party_type === 'Temporary Worker';
		const $row = $(
			`<div class="ax-result" tabindex="0" role="button">` +
				`<span class="indicator-pill no-indicator-dot ${is_tw ? 'orange' : 'green'}">${
					is_tw ? __('Temp') : __('Emp')
				}</span>` +
				`<span class="ax-result-label">${frappe.utils.escape_html(row.label || '')}</span>` +
				`<span class="ax-result-sub text-muted"><bdi>${frappe.utils.escape_html(row.sub || '')}</bdi></span></div>`
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
			? `<span class="ax-active-bed">${__('Bed')}: <bdi>${frappe.utils.escape_html(bed)}</bdi></span>`
			: `<span class="ax-active-hint">${__('Click a free bed to house him.')}</span>`;
		this.$active.html(
			`<div class="ax-active-card"><div class="ax-active-head">` +
				`<span class="ax-active-name">${frappe.utils.escape_html(card.worker_name || card.party)}</span>` +
				`<span class="indicator-pill no-indicator-dot ${is_tw ? 'orange' : 'green'}">${
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

	// [#2gxwhl]
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
				// [#dvlqkx]
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
		// [#jw9kx4]
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
			const $item = $('<div class="ax-cart-item"></div>')
				.html(
					`<span class="ax-cart-name">${frappe.utils.escape_html(c.label || c.party)}</span>` +
						`<span class="ax-cart-bed text-muted"><bdi>${frappe.utils.escape_html(c.bed || '')}</bdi></span>`
				)
				.appendTo($list);
			// [#smadir]
			$('<button class="btn btn-xs btn-link ax-cart-checkin"></button>')
				.text(__('Check-in slip'))
				.on('click', () => this._print_checkin(c))
				.appendTo($item);
		});
	}

	// [#33np9k]
	_render_deck() {
		this.$deck.empty();
		this._render_stages();
		if (!this.cart.length) return;
		if (this.catalog == null) this._load_catalog();
		const $cust = $('<section class="ax-deck-sec"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Custody Handover')).appendTo($cust);
		const $list = $('<div class="ax-deck-list"></div>').appendTo($cust);
		this.cart.forEach((c) => this._custody_row($list, c));
		// [#gk3q62]
		const $card = $('<section class="ax-deck-sec"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Arrival Card')).appendTo($card);
		const $clist = $('<div class="ax-deck-list"></div>').appendTo($card);
		this.cart.forEach((c) => this._card_row($clist, c));
		// [#co0grg]
		const pendingQr = this.cart.filter((c) => c.party_type === 'Employee' && !c._card_done);
		if (pendingQr.length) {
			$('<button class="btn btn-sm btn-default ax-qr-all"></button>')
				.text(__('Create QR for all ({0})', [pendingQr.length]))
				.on('click', () => this._issue_group_qr())
				.appendTo($card);
		}
		// [#q1rgj9]
		$('<button class="btn btn-sm btn-default ax-cards-all"></button>')
			.text(__('Print arrival cards ({0})', [this.cart.length]))
			.on('click', () => this._print_all_cards())
			.appendTo($card);
		this.$qrBlock = $('<div class="ax-qr-block"></div>').appendTo($card);
		this._render_qr_block();
		this._transport_section();
	}

	_load_catalog() {
		// [#ln7hst]
		this.catalog = [];
		if (!this.building) return;
		frappe
			.call({
				method: 'apex_habitat.habitat.api.custody_kiosk.get_kiosk_catalog',
				args: { building: this.building },
			})
			.then((r) => {
				this.catalog = (r.message && r.message.articles) || [];
				if (this.cart.length) this._render_deck(); // refill the selects now the catalog is in
			})
			.catch(() => {
				this.catalog = [];
			});
	}

	_custody_row($list, c) {
		const $row = $('<div class="ax-deck-row"></div>').appendTo($list);
		$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
		if (c.party_type === 'Temporary Worker') {
			// [#fkt5z4]
			$('<span class="indicator-pill no-indicator-dot orange"></span>')
				.text(__('Custody deferred'))
				.appendTo($row);
			return;
		}
		if (c._custody_issue) {
			$('<span class="indicator-pill no-indicator-dot green"></span>').text(__('Issued')).appendTo($row);
			// [#98wano]
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

	// [#ta7hge]
	_custody_cart($row, c) {
		if ($row.find('.ax-custody-cart').length) return; // already open
		$row.find('.ax-deck-btn').remove();
		c._custody_lines = c._custody_lines || [];
		const $panel = $('<div class="ax-custody-cart"></div>').appendTo($row);
		const $lines = $('<div class="ax-custody-lines"></div>').appendTo($panel);
		const $add = $('<div class="ax-custody-add"></div>').appendTo($panel);
		const $foot = $('<div class="ax-custody-foot"></div>').appendTo($panel);
		const $issue = $('<button class="btn btn-sm btn-primary"></button>').appendTo($foot);

		const $sel = $('<select class="form-control form-control-sm ax-custody-article"></select>').appendTo($add);
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
		).appendTo($add);

		const renderLines = () => {
			$lines.empty();
			c._custody_lines.forEach((l, i) => {
				const $li = $('<div class="ax-custody-line"></div>').appendTo($lines);
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
				method: 'apex_habitat.habitat.api.custody_kiosk.issue_cart',
				args: {
					employee: c.party, // an Employee party — issue_cart posts to his ledger
					building: this.building,
					items_json: JSON.stringify(c._custody_lines.map((l) => ({ article: l.article, qty: l.qty }))),
				},
				freeze: true,
				freeze_message: __('Issuing custody…'),
				callback: (r) => {
					if (r.exc || !r.message) return;
					c._custody_issue = r.message.custody_issue; // kept for the handover print (later)
					this.custodyIssued = true;
					frappe.show_alert({ message: __('Custody issued to {0}', [c.label]), indicator: 'green' });
					this._render_stages();
					this._render_deck();
				},
			});
		});
		renderLines();
	}

	_card_row($list, c) {
		const $row = $('<div class="ax-deck-row"></div>').appendTo($list);
		$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
		if (c.party_type === 'Employee') {
			if (c._card_done) {
				$('<span class="indicator-pill no-indicator-dot green"></span>').text(__('QR issued')).appendTo($row);
			}
		} else {
			// [#1jl7r0]
			$('<span class="indicator-pill no-indicator-dot orange"></span>')
				.text(__('Link after registration'))
				.appendTo($row);
		}
		$('<button class="btn btn-sm btn-default"></button>')
			.text(__('Print slip'))
			.on('click', () => this._print_slip(c))
			.appendTo($row);
	}

	// [#bw83vt]
	_issue_group_qr() {
		const employees = this.cart
			.filter((c) => c.party_type === 'Employee' && !c._card_done)
			.map((c) => c.party);
		if (!employees.length) return;
		frappe.call({
			method: 'apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.batch_issue_worker_links',
			args: { employees_json: JSON.stringify(employees) },
			freeze: true,
			freeze_message: __('Creating QR codes…'),
			callback: (r) => {
				if (r.exc || !r.message) return;
				(r.message || []).forEach((m) => {
					const c = this.cart.find((x) => x.party_type === 'Employee' && x.party === m.employee);
					if (c) {
						c._card_done = true;
						c._card_qr = m; // {link, qr, phone} — rendered inline, never in a dialog
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
		});
	}

	_render_qr_block() {
		this.$qrBlock.empty();
		this.cart
			.filter((c) => c._card_qr)
			.forEach((c) => {
				const m = c._card_qr;
				const $item = $('<div class="ax-qr-item"></div>').appendTo(this.$qrBlock);
				$('<div class="ax-qr-name"></div>').text(c.label || c.party).appendTo($item);
				if (m.qr) $('<img class="ax-qr-img" alt="QR" />').attr('src', m.qr).appendTo($item);
				// isolate the LTR Masar URL so it keeps order inside the RTL deck
				const $link = $('<a class="ax-qr-link" target="_blank" rel="noopener"></a>').attr('href', m.link);
				$('<bdi></bdi>').text(m.link).appendTo($link);
				$link.appendTo($item);
			});
	}

	// [#9szus4]
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
			method: 'apex_habitat.habitat.api.arrivals_desk.get_arrival_slip',
			args: { party_type: c.party_type, party: c.party },
			callback: (r) => {
				if (r.exc || !r.message) return;
				this._open_print(r.message.title, r.message.html);
			},
		});
	}

	// [#2f9r49]
	_print_checkin(c) {
		frappe.call({
			method: 'apex_habitat.habitat.api.arrivals_desk.get_checkin_slip',
			args: { party_type: c.party_type, party: c.party },
			callback: (r) => {
				if (r.exc || !r.message) return;
				this._open_print(r.message.title, r.message.html);
			},
		});
	}

	// [#1b6a7h]
	_print_custody(c) {
		if (!c._custody_issue) {
			frappe.show_alert({ message: __('Issue custody first'), indicator: 'orange' });
			return;
		}
		frappe.call({
			method: 'apex_habitat.habitat.api.arrivals_desk.get_custody_handover_slip',
			args: { custody_issue: c._custody_issue },
			callback: (r) => {
				if (r.exc || !r.message) return;
				this._open_print(r.message.title, r.message.html);
			},
		});
	}

	// [#6fkydb]
	_print_all_cards() {
		if (!this.cart.length) return;
		const calls = this.cart.map((c) =>
			frappe.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.get_arrival_slip',
				args: { party_type: c.party_type, party: c.party },
			})
		);
		frappe.dom.freeze(__('Building arrival cards…'));
		// [#lkskns]
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
		const $tr = $('<section class="ax-deck-sec"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Transport')).appendTo($tr);
		const $tlist = $('<div class="ax-deck-list"></div>').appendTo($tr);
		const employees = this.cart.filter((c) => c.party_type === 'Employee');
		const tws = this.cart.filter((c) => c.party_type === 'Temporary Worker');
		employees.forEach((c) => {
			const $row = $('<label class="ax-deck-row ax-tr-row"></label>').appendTo($tlist);
			$('<input type="checkbox" checked />').attr('data-party', c.party).appendTo($row);
			$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
		});
		tws.forEach((c) => {
			const $row = $('<div class="ax-deck-row"></div>').appendTo($tlist);
			$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
			// [#3b4x9r]
			$('<span class="indicator-pill no-indicator-dot orange"></span>')
				.text(__('Unregistered manifest'))
				.appendTo($row);
		});
		if (employees.length) {
			$('<button class="btn btn-sm btn-default ax-tr-go"></button>')
				.text(__('Create one transport request'))
				.on('click', () => this._create_transport($tlist))
				.appendTo($tr);
		} else if (tws.length) {
			$('<div class="ax-tr-note text-muted"></div>')
				.text(__('Temporary workers board via the trip’s unregistered manifest.'))
				.appendTo($tr);
		}
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
		this.transportStarted = true;
		this._render_stages();
		// [#3z6pcn]
		frappe.new_doc('Transport Request', {
			service_line: 'Site Transport',
			request_type: 'Accommodation to Project Shuttle',
			project: this.project || undefined,
			accommodation_building: this.building || undefined,
			workers,
		});
	}

	// [#fltkjy]
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
		// [#r6fpkn]
		const chips = [
			['building', __('Building'), !!this.building],
			['housed', __('Housed'), housed],
			['custody', __('Custody'), this.custodyIssued],
			['card', __('Card'), this.cardIssued],
			['transport', __('Transport'), this.transportStarted],
		];
		const firstTodo = chips.findIndex(([, , done]) => !done);
		this.$stages.html(
			chips
				.map(([k, label, done], i) => {
					const color = done ? 'green' : i === firstTodo ? 'blue' : 'gray';
					return (
						`<span class="indicator-pill no-indicator-dot ${color}" data-stage="${k}">` +
						`${frappe.utils.escape_html(label)}</span>`
					);
				})
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
		// [#b9r9iq]
		const readiness =
			room.readiness_status && room.readiness_status !== 'Ready' && room.readiness_status !== 'Unknown'
				? ` · ${frappe.utils.escape_html(__(room.readiness_status))}`
				: '';
		// [#ga6klw]
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
		const a11y = color === 'green' ? ' tabindex="0" role="button"' : ''; // free beds are keyboard-reachable
		const name = bed.occupant ? bed.occupant.employee_name || bed.occupant.employee || '' : '';
		const occupant = bed.occupant
			? `<span class="ax-bed-occupant" title="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(
					name
			  )}</span>`
			: '';
		const custody =
			bed.occupant && bed.occupant.has_custody
				? `<span class="ax-bed-badge" title="${__('Has custody')}">●</span>`
				: '';
		return (
			`<div class="ax-bed ax-bed--${color}${temp}" data-bed="${frappe.utils.escape_html(bed.bed || '')}"${a11y} ` +
			`title="${frappe.utils.escape_html(bed.bed_code || '')}">` +
			`<span class="ax-bed-code"><bdi>${frappe.utils.escape_html(bed.bed_code || '')}</bdi></span>` +
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
