// Copyright (c) 2026, afmcoltd

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
		this.$root = $('<div class="arrivals-desk"></div>').appendTo(this.page.main);
		this._build_strip();
		this.$body = $('<div class="ax-body"></div>').appendTo(this.$root);

		this.$intake = $('<aside class="ax-zone ax-zone-intake"></aside>').appendTo(this.$body);
		$('<div class="ax-zone-head"></div>').text(__('Who is arriving?')).appendTo(this.$intake);

		this.$floorZone = $('<section class="ax-zone ax-zone-floor"></section>').appendTo(this.$body);
		this.$anchor = $('<div class="ax-anchor ax-zone-head"></div>').appendTo(this.$floorZone);
		this.$capacity = $('<div class="ax-capacity"></div>').appendTo(this.$anchor);
		this.$stages = $('<div class="ax-stages"></div>').appendTo(this.$anchor);
		this.$floor = $('<div class="ax-floor"></div>').appendTo(this.$floorZone);
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

		this.$actions = $('<aside class="ax-zone ax-zone-actions"></aside>').appendTo(this.$body);
		$('<div class="ax-zone-head"></div>').text(__('This session')).appendTo(this.$actions);

		this._build_intake();
	}

	_build_strip() {
		this.$strip = $('<div class="ax-strip" role="status" aria-live="polite"></div>').appendTo(this.$root);
		const stat = (key, label) => {
			const $cell = $('<div class="ax-strip-stat"></div>').appendTo(this.$strip);
			$('<div class="ax-strip-num">—</div>').appendTo($cell).attr('data-stat', key);
			$('<div class="ax-strip-label"></div>').text(label).appendTo($cell);
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
		const $bWrap = $('<div class="ax-anchor-field"></div>').prependTo(this.$anchor);
		const $pWrap = $('<div class="ax-anchor-field"></div>').insertAfter($bWrap);

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
			`<input type="search" class="ax-search-input form-control form-control-sm" placeholder="${__(
				'Search worker name or passport…'
			)}" />`
		).appendTo($search);
		this.$results = $('<div class="ax-results"></div>').appendTo($search);
		this.$manifest = $('<div class="ax-manifest"></div>').appendTo(this.$intake);
		this.$active = $('<div class="ax-active"></div>').appendTo(this.$intake);
		this.$cart = $('<div class="ax-cart"></div>').appendTo(this.$actions);
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
			.text(__("Today's expected arrivals ({0})", [data.total]))
			.appendTo(this.$manifest);
		$('<div class="ax-manifest-tally text-muted"></div>')
			.text(__('{0} of {1} arrived, {2} pending', [data.arrived, data.total, data.pending]))
			.appendTo(this.$manifest);
		const $list = $('<div class="ax-manifest-list"></div>').appendTo(this.$manifest);
		workers.forEach((w) => this._manifest_row($list, w));
	}

	_manifest_row($list, w) {
		const $row = $(
			`<div class="ax-manifest-row${w.arrived ? ' ax-manifest-row--done' : ''}" tabindex="0" role="button"></div>`
		).appendTo($list);
		$('<span class="ax-manifest-tick"></span>')
			.text(w.arrived ? '✓' : '○')
			.appendTo($row);
		$('<span class="ax-manifest-name"></span>').text(w.worker_name || '').appendTo($row);
		if (w.passport_number) {
			$('<span class="ax-manifest-sub text-muted"></span>')
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
			'<div class="ax-results-skeleton" aria-hidden="true">' +
				'<div class="ax-result-ghost"></div>'.repeat(3) +
				'</div>'
		);
	}

	_render_search_error() {
		this.$results.empty();
		const $row = $('<div class="ax-results-error"></div>').appendTo(this.$results);
		$('<div class="ax-results-error-msg"></div>')
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
			$('<div class="ax-results-empty text-muted"></div>').text(msg).appendTo(this.$results);
		}
		this._append_register_row();
	}

	_append_register_row() {
		$('<button class="btn btn-default btn-sm ax-register-row"></button>')
			.html(`<span class="ax-register-plus">+</span> ${__('Register new arrival by passport')}`)
			.on('click', () => this._open_register_modal())
			.appendTo(this.$results);
	}

	_result_row(row) {
		const is_tw = row.party_type === 'Temporary Worker';
		const $row = $(
			'<div class="ax-result" tabindex="0" role="button">' +
				`<span class="indicator-pill no-indicator-dot ${is_tw ? 'orange' : 'green'}">${
					is_tw ? __('Temp') : __('Emp')
				}</span>` +
				`<span class="ax-result-label">${frappe.utils.escape_html(row.label || '')}</span>` +
				`<span class="ax-result-sub text-muted"><bdi>${frappe.utils.escape_html(row.sub || '')}</bdi></span>` +
				`${this._expiry_chip(row)}</div>`
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
		this.$active.html(
			`<div class="ax-active-card ax-active-card--load text-muted">${__('Loading…')}</div>`
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
		const $card = $('<div class="ax-active-card ax-active-card--err"></div>').appendTo(
			this.$active.empty()
		);
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
			? `<span class="ax-active-bed">${__('Bed')}: <bdi>${frappe.utils.escape_html(bed)}</bdi></span>`
			: `<span class="ax-active-hint">${__('Click a free bed to house him.')}</span>`;
		this.$active.html(
			'<div class="ax-active-card"><div class="ax-active-head">' +
				`<span class="ax-active-name">${frappe.utils.escape_html(card.worker_name || card.party)}</span>` +
				`<span class="indicator-pill no-indicator-dot ${is_tw ? 'orange' : 'green'}">${
					is_tw ? __('Temporary Worker') : __('Employee')
				}</span>${this._expiry_chip(card)}</div>` +
				`<div class="ax-active-sub text-muted">${
					card.project ? frappe.utils.escape_html(card.project) : __('No project yet')
				}</div>` +
				`<div class="ax-active-foot">${foot}</div></div>`
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
					$bed.toggleClass('ax-bed--busy', state);
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
				.removeAttr('tabindex role');
		}
		const rollback = () => {
			if ($bed && $bed.length) {
				$bed.removeClass('ax-bed--red ax-bed--busy')
					.addClass('ax-bed--green')
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
				if ($bed && $bed.length) $bed.removeClass('ax-bed--busy');
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
			this.$results.find('.ax-result').removeClass('ax-result--active');
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
			.text(__('Arrived this session ({0})', [this.cart.length]))
			.appendTo(this.$cart);
		const $list = $('<div class="ax-cart-list"></div>').appendTo(this.$cart);
		this.cart.forEach((c) => {
			const dots = this._cart_dots(c);
			const $item = $(`<div class="ax-cart-item${dots.complete ? ' ax-cart-item--done' : ''}"></div>`)
				.html(
					`<span class="ax-cart-name">${frappe.utils.escape_html(c.label || c.party)}</span>` +
						`<span class="ax-cart-bed text-muted"><bdi>${frappe.utils.escape_html(c.bed || '')}</bdi></span>`
				)
				.appendTo($list);
			$('<div class="ax-cart-dots"></div>').html(dots.html).appendTo($item);
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
		const dot = (label, state) => {
			const mark = state === null ? '–' : state ? '✓' : '–';
			const cls = state === null ? 'na' : state ? 'on' : 'off';
			return `<span class="ax-cart-dot ax-cart-dot--${cls}">${frappe.utils.escape_html(label)} ${mark}</span>`;
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
		const $cust = $('<section class="ax-deck-sec" data-stage-target="custody"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Custody Handover')).appendTo($cust);
		if (this.catalogError) {
			const $err = $('<div class="ax-catalog-error"></div>').appendTo($cust);
			$('<span></span>').text(__("Couldn't load custody store — retry")).appendTo($err);
			$('<button class="btn btn-xs btn-default ax-catalog-retry"></button>')
				.text(__('Retry'))
				.on('click', () => this._retry_catalog())
				.appendTo($err);
		}
		const $list = $('<div class="ax-deck-list"></div>').appendTo($cust);
		this.cart.forEach((c) => this._custody_row($list, c));
		const $card = $('<section class="ax-deck-sec" data-stage-target="card"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Arrival Card')).appendTo($card);
		const $clist = $('<div class="ax-deck-list"></div>').appendTo($card);
		this.cart.forEach((c) => this._card_row($clist, c));
		const pendingQr = this.cart.filter((c) => c.party_type === 'Employee' && !c._card_done);
		if (pendingQr.length) {
			$('<button class="btn btn-sm btn-default ax-qr-all"></button>')
				.text(__('Create QR for all ({0})', [pendingQr.length]))
				.on('click', () => this._issue_group_qr())
				.appendTo($card);
		}
		$('<button class="btn btn-sm btn-default ax-cards-all"></button>')
			.text(__('Print arrival cards ({0})', [this.cart.length]))
			.on('click', () => this._print_all_cards())
			.appendTo($card);
		this.$qrBlock = $('<div class="ax-qr-block"></div>').appendTo($card);
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
		const $row = $('<div class="ax-deck-row"></div>').appendTo($list);
		$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
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
		const $panel = $('<div class="ax-custody-cart"></div>').appendTo($row);
		const $lines = $('<div class="ax-custody-lines"></div>').appendTo($panel);
		const $add = $('<div class="ax-custody-add"></div>').appendTo($panel);
		const $foot = $('<div class="ax-custody-foot"></div>').appendTo($panel);
		const $issue = $('<button class="btn btn-sm btn-primary ax-custody-issue"></button>').appendTo($foot);

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
			// One token per cart submission, reused if the operator retries a request that
			// timed out: the server returns the issue it already created rather than
			// decrementing the building store a second time.
			c._issue_token = c._issue_token || frappe.utils.get_random(24);
			frappe.call({
				method: 'apex.habitat.api.custody_kiosk.issue_cart',
				args: {
					employee: c.party,
					building: this.building,
					items_json: JSON.stringify(c._custody_lines.map((l) => ({ article: l.article, qty: l.qty }))),
					request_token: c._issue_token,
				},
				freeze: true,
				freeze_message: __('Issuing custody…'),
				callback: (r) => {
					if (r.exc || !r.message) return;
					c._issue_token = null;
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
		const $row = $('<div class="ax-deck-row"></div>').appendTo($list);
		$('<span class="ax-deck-name"></span>').text(c.label || c.party).appendTo($row);
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
				const $item = $('<div class="ax-qr-item"></div>').appendTo(this.$qrBlock);
				$('<div class="ax-qr-name"></div>').text(c.label || c.party).appendTo($item);
				if (c._card_pending) {
					$('<div class="ax-qr-pending"></div>')
						.html('<span class="ax-qr-spinner" aria-hidden="true"></span>')
						.append(document.createTextNode(__('Creating QR…')))
						.appendTo($item);
					return;
				}
				const m = c._card_qr;
				if (m.qr) $('<img class="ax-qr-img" alt="QR" />').attr('src', m.qr).appendTo($item);
				const $link = $('<a class="ax-qr-link" target="_blank" rel="noopener"></a>').attr('href', m.link);
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
						message: __('Messaging gateway is not configured yet (Salis Settings).'),
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
		/* The print window is its own document — the Desk page stylesheet never reaches it,
		   so the one rule it needs travels with it. */
		w.document.write(
			`<html><head><title>${frappe.utils.escape_html(title || '')}</title>` +
				'<style>.ax-print-break{page-break-after:always}</style></head>' +
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
					.join('<div class="ax-print-break"></div>');
				if (html) this._open_print(__('Arrival Cards'), html);
			})
			.catch(() => {})
			.then(() => frappe.dom.unfreeze());
	}

	_transport_section() {
		const $tr = $('<section class="ax-deck-sec" data-stage-target="transport"></section>').appendTo(this.$deck);
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
		const $cap = $('<div class="ax-cap-wrap"></div>');
		$('<span class="ax-cap-title"></span>').text(grid.building_title || '').appendTo($cap);
		const $meter = $(
			`<div class="ax-cap-meter" role="img" ` +
				`aria-label="${__('{0} free of {1} beds', [free, total])}" ` +
				`title="${__('{0} free of {1} beds', [free, total])}"></div>`
		).appendTo($cap);
		$('<div class="ax-cap-fill ax-cap-fill--free"></div>')
			.css('width', `${Math.round((free / denom) * 100)}%`)
			.appendTo($meter);
		$('<div class="ax-cap-fill ax-cap-fill--occ"></div>')
			.css('width', `${Math.round((physOcc / denom) * 100)}%`)
			.appendTo($meter);
		if (over) {
			$('<div class="ax-cap-fill ax-cap-fill--over"></div>')
				.css('width', `${Math.round((over / denom) * 100)}%`)
				.appendTo($meter);
		}
		const legend = (variant, label) => {
			const $l = $(`<div class="ax-cap-legend ax-cap-legend--${variant}"></div>`).appendTo($cap);
			$('<span class="ax-cap-swatch"></span>').appendTo($l);
			$('<span></span>').text(label).appendTo($l);
		};
		legend('free', __('{0} free', [free]));
		legend('occ', __('{0} occupied', [occupied]));
		if (over) legend('over', __('{0} over capacity', [over]));
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
			);
			$('<span class="ax-step-num"></span>')
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
						'<section class="ax-floor-group"><header class="ax-floor-header">' +
						`${frappe.utils.escape_html(floor.floor_label || '')}</header>` +
						`<div class="ax-rooms">${rooms}</div></section>`
					);
				})
				.join('')
		);
		if (summary.total_beds > 0 && !summary.available) {
			$('<div class="ax-floor-banner"></div>')
				.text(__('This building has rooms but every bed is occupied — use Over-capacity'))
				.prependTo(this.$floor);
		}
	}

	_room_html(room) {
		const beds = (room.beds || []).map((bed) => this._bed_html(bed, room.readiness_status)).join('');
		const occ = `${room.current_occupancy || 0}/${room.bed_capacity || 0}`;
		const sameProject = !!(this.project && room.dominant_project && room.dominant_project === this.project);
		const projClass = sameProject ? ' ax-room--same-project' : '';
		const projBadge = sameProject
			? `<span class="ax-room-proj" title="${__('Same project as the selected worker')}">${__('Same project')}</span>`
			: '';
		const readiness =
			room.readiness_status && room.readiness_status !== 'Ready' && room.readiness_status !== 'Unknown'
				? ` · ${frappe.utils.escape_html(__(room.readiness_status))}`
				: '';
		const has_free = (room.beds || []).some((b) => b.bed_color === 'green');
		const oc = has_free
			? ''
			: `<button class="ax-room-oc" data-room="${frappe.utils.escape_html(room.room || '')}" ` +
			  `title="${__('House over capacity in a temporary bed')}">+ ${__('Over-capacity')}</button>`;
		return (
			`<div class="ax-room${projClass}"><div class="ax-room-header">` +
			`<span class="ax-room-number">${frappe.utils.escape_html(room.room_number || room.room || '')}${projBadge}</span>` +
			`<span class="ax-room-meta">${occ}${readiness}</span></div>` +
			`<div class="ax-beds">${beds}</div>${oc}</div>`
		);
	}

	_bed_html(bed, readiness_status) {
		const color = bed.bed_color || 'grey';
		const temp = bed.is_temporary ? ' ax-bed--temp' : '';
		const a11y = color === 'green' || color === 'red' ? ' tabindex="0" role="button"' : '';
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
		const blocker =
			color === 'amber' && readiness_status && readiness_status !== 'Ready' && readiness_status !== 'Unknown'
				? `<span class="ax-bed-blocker">${frappe.utils.escape_html(__(readiness_status))}</span>`
				: '';
		const tempChip = bed.is_temporary
			? `<span class="ax-bed-chip ax-bed-chip--temp">${__('Temp')}</span>`
			: '';
		return (
			`<div class="ax-bed ax-bed--${color}${temp}" data-bed="${frappe.utils.escape_html(bed.bed || '')}"${a11y} ` +
			`title="${frappe.utils.escape_html(bed.bed_code || '')}">` +
			`<span class="ax-bed-code"><bdi>${frappe.utils.escape_html(bed.bed_code || '')}</bdi>${tempChip}</span>` +
			`${occupant}${blocker}${custody}</div>`
		);
	}

	_render_empty(msg) {
		this.$floor.html(`<div class="ax-empty">${frappe.utils.escape_html(msg)}</div>`);
	}

	_render_loading() {
		this.$floor.html(
			`<div class="ax-skeleton">${'<div class="ax-skeleton-room"></div>'.repeat(6)}</div>`
		);
	}

	_render_error() {
		this.$floor.html(
			'<div class="ax-error"><div class="ax-error-msg">' +
				`${__('Could not load the building. Please retry.')}</div>` +
				`<button class="btn btn-default btn-sm ax-retry">${__('Retry')}</button></div>`
		);
		this.$floor.find('.ax-retry').on('click', () => this.refresh());
	}
}
