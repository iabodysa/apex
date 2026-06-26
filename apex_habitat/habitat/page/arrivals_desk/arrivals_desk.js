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
		this._load_strip();
		this._render_empty(__('Pick a building to start the arrival.'));
	}

	_build_skeleton() {
		this.$root = $('<div class="arrivals-desk"></div>').appendTo(this.page.main);
		// Read-only telemetry strip (Arrivals today / Pending on manifest), building-agnostic.
		this._build_strip();
		// [#b5ku2i]
		this.$body = $('<div class="ax-body"></div>').appendTo(this.$root);

		// [#nzjhbw]
		this.$intake = $('<aside class="ax-zone ax-zone-intake"></aside>').appendTo(this.$body);
		// Sticky zone header so the "who is arriving?" question stays pinned on scroll.
		$('<div class="ax-zone-head"></div>').text(__('Who is arriving?')).appendTo(this.$intake);

		// [#awqamr]
		this.$floorZone = $('<section class="ax-zone ax-zone-floor"></section>').appendTo(this.$body);
		// The Floor's sticky header is the building + capacity anchor.
		this.$anchor = $('<div class="ax-anchor ax-zone-head"></div>').appendTo(this.$floorZone);
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
		this.$floor.on('keydown', '.ax-bed--green, .ax-bed--red', (e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				this._on_bed_click(e);
			}
		});

		// [#mo583e]
		this.$actions = $('<aside class="ax-zone ax-zone-actions"></aside>').appendTo(this.$body);
		// Sticky zone header naming the right-hand "this session" work area.
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
		// Read-only counts from the shared Custom Number Card methods; failures
		// leave the dash placeholder rather than breaking the desk.
		const set = (key, val) =>
			this.$strip.find(`[data-stat="${key}"]`).text(frappe.format(val, { fieldtype: 'Int' }));
		frappe
			.xcall('apex_habitat.habitat.api.dashboard.get_arrivals_today')
			.then((v) => set('arrivals_today', v))
			.catch(() => {});
		frappe
			.xcall('apex_habitat.habitat.api.dashboard.get_pending_on_manifest')
			.then((v) => set('pending_on_manifest', v))
			.catch(() => {});
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
			this._load_manifest(); // manifest is building-scoped
		} else if (!val && this.building) {
			// [#df9hzt]
			this.building = null;
			this.grid = null;
			this.catalog = null;
			this._render_stages();
			this._render_capacity(null);
			this._render_empty(__('Pick a building to start the arrival.'));
			this._load_manifest();
		}
	}

	_on_project_change() {
		this.project = this.project_field.get_value() || null;
		// Re-tint rooms for the newly selected project (uses the cached grid; no refetch).
		if (this.grid) this._render_grid(this.grid);
	}

	refresh() {
		this._load_strip();
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
		// Note: do NOT empty $intake — it carries the sticky zone header from _build_skeleton.
		const $search = $('<div class="ax-search"></div>').appendTo(this.$intake);
		this.$search_input = $(
			`<input type="search" class="ax-search-input form-control form-control-sm" placeholder="${__(
				'Search worker name or passport…'
			)}" />`
		).appendTo($search);
		this.$results = $('<div class="ax-results"></div>').appendTo($search);
		// Today's expected-arrivals manifest (from Arrival Batch), below the search.
		this.$manifest = $('<div class="ax-manifest"></div>').appendTo(this.$intake);
		this.$active = $('<div class="ax-active"></div>').appendTo(this.$intake);
		this.$cart = $('<div class="ax-cart"></div>').appendTo(this.$actions);
		this.$deck = $('<div class="ax-deck"></div>').appendTo(this.$actions); // stage deck
		this.$search_input.on('input', frappe.utils.debounce(() => this._search(), 250));
		this._render_results(null);
		this._render_cart();
		this._load_manifest();
	}

	// Pull today's expected arrivals for the picked building (refreshed with the grid).
	_load_manifest() {
		if (!this.$manifest) return;
		frappe
			.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.get_expected_arrivals',
				args: { building: this.building },
			})
			.then((r) => this._render_manifest(r.message))
			.catch(() => this.$manifest.empty());
	}

	_render_manifest(data) {
		this.$manifest.empty();
		const workers = (data && data.workers) || [];
		if (!workers.length) return; // no manifest for today → keep the intake clean
		$('<div class="ax-manifest-title"></div>')
			.text(__("Today's expected arrivals ({0})", [data.total]))
			.appendTo(this.$manifest);
		// Running tally: how many of the manifest have arrived vs still pending.
		$('<div class="ax-manifest-tally text-muted"></div>')
			.text(__('{0} of {1} arrived, {2} pending', [data.arrived, data.total, data.pending]))
			.appendTo(this.$manifest);
		const $list = $('<div class="ax-manifest-list"></div>').appendTo(this.$manifest);
		workers.forEach((w) => this._manifest_row($list, w));
	}

	_manifest_row($list, w) {
		const $row = $(`<div class="ax-manifest-row${w.arrived ? ' ax-manifest-row--done' : ''}" tabindex="0" role="button"></div>`).appendTo(
			$list
		);
		$('<span class="ax-manifest-tick"></span>').text(w.arrived ? '✓' : '○').appendTo($row);
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

	// Tapping a manifest row: an already-matched worker is preselected; an
	// unmatched one pre-fills the passport register modal with the manifest data.
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
			batch_row: w.row, // link back so this manifest line ticks on register
		});
	}

	_search() {
		const txt = (this.$search_input.val() || '').trim();
		this._searched = true;
		this._render_search_skeleton(); // ghost rows while the lookup is in flight
		frappe
			.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.search_arrivals_workers',
				args: { building: this.building, txt },
			})
			.then((r) => this._render_results(r.message || []))
			// A rejected search is its own state (retry), never a silent "zero matches".
			.catch(() => this._render_search_error());
	}

	// Three ghost rows so an in-flight search reads as loading, not as empty.
	_render_search_skeleton() {
		this.$results.html(
			`<div class="ax-results-skeleton" aria-hidden="true">` +
				'<div class="ax-result-ghost"></div>'.repeat(3) +
				'</div>'
		);
	}

	// Distinct error state: a rejection is visually different from zero matches.
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
			// null = first run (no search yet) → guidance; [] after a search → no match.
			const msg = this._searched
				? __('No registered workers match. Register a new arrival below.')
				: __('Search a name or passport, or register a new arrival');
			$('<div class="ax-results-empty text-muted"></div>').text(msg).appendTo(this.$results);
		}
		this._append_register_row();
	}

	// [#2tv16z]
	_append_register_row() {
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
		this.$active.html(`<div class="ax-active-card ax-active-card--load text-muted">${__('Loading…')}</div>`);
		frappe
			.call({
				method: 'apex_habitat.habitat.api.arrivals_desk.get_arrival_card',
				args: { party_type: row.party_type, party: row.party },
			})
			.then((r) => this._render_active_card(r.message))
			.catch(() => this._render_active_card_error(row));
	}

	// Failure branch keeps the existing message but adds a Retry that re-fires the fetch.
	_render_active_card_error(row) {
		const $card = $('<div class="ax-active-card ax-active-card--err"></div>').appendTo(this.$active.empty());
		$('<div class="text-muted"></div>').text(__('Could not load the worker.')).appendTo($card);
		$('<button class="btn btn-default btn-xs ax-active-retry"></button>')
			.text(__('Retry'))
			.on('click', () => this._select_worker(row))
			.appendTo($card);
	}

	// Amber "window ends" / red "expired" chip from the server-computed
	// expiry_days (negative = lapsed). Returns '' for an Employee or no window.
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
			`<div class="ax-active-card"><div class="ax-active-head">` +
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
		// prefill (optional) seeds the form from a tapped Arrival Batch manifest row.
		const pf = prefill || {};
		const d = new frappe.ui.Dialog({
			title: __('Register New Arrival (Passport)'),
			fields: [
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
					options: 'Accommodation Building',
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
					method: 'apex_habitat.habitat.api.arrivals_desk.register_temporary_worker',
					// carry the manifest row (if any) so its line ticks on register
					args: { ...values, batch_row: pf.batch_row || null },
					freeze: true,
					freeze_message: __('Registering…'),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						frappe.show_alert({ message: __('Registered: {0}', [r.message.label]), indicator: 'green' });
						this._select_worker(r.message); // make the new arrival active
						this._search(); // refresh the result list
						this._load_manifest(); // tick the just-registered manifest line
					},
				});
			},
		});
		// Tag the modal so the mobile breakpoint can present it as a full-screen sheet.
		d.$wrapper.addClass('ax-register-modal');
		d.show();
	}

	// [#2gxwhl]
	_on_bed_click(e) {
		const $bed = $(e.currentTarget);
		// A red/occupied bed opens checkout so Arrivals can also turn a bed over.
		if ($bed.hasClass('ax-bed--red')) {
			this._open_check_out($bed.attr('data-bed'), $bed);
			return;
		}
		if (!$bed.hasClass('ax-bed--green')) return; // amber/grey are not actionable here
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

	// Find the occupant payload for a bed from the in-memory grid model.
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

	// Checkout from the Arrivals floor, mirroring Front Desk: a resident WITH custody
	// goes straight to the full Accommodation Checkout form; otherwise quick_check_out
	// (the existing write path — no new endpoint) does a one-click checkout.
	_open_check_out(bed, $bed) {
		const occupant = this._bed_occupant(bed) || {};
		if (occupant.has_custody) {
			const d = new frappe.ui.Dialog({
				title: __('Quick Check-out'),
				fields: [
					{
						fieldname: 'msg',
						fieldtype: 'HTML',
						options: `<div>${__('This resident has custody items. Opening the full Checkout form to clear custody.')}</div>`,
					},
				],
				primary_action_label: __('Open Checkout Form'),
				primary_action: () => {
					d.hide();
					frappe.new_doc('Accommodation Checkout', { assignment: occupant.assignment });
				},
			});
			d.show();
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __('Quick Check-out'),
			fields: [
				{
					fieldname: 'context',
					fieldtype: 'HTML',
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(
						occupant.employee_name || ''
					)}</div>`,
				},
				{
					fieldname: 'checkout_date',
					label: __('Check-out Date'),
					fieldtype: 'Date',
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{
					fieldname: 'checkout_reason',
					label: __('Check-out Reason'),
					fieldtype: 'Select',
					reqd: 1,
					options: '\nFinal Exit\nInternal Transfer\nProject Transfer\nAbsconding\nEnd of Contract',
				},
				{
					fieldname: 'room_condition_snapshot',
					label: __('Room Condition Snapshot'),
					fieldtype: 'Attach Image',
				},
			],
			primary_action_label: __('Check Out'),
			primary_action: (values) => {
				d.hide();
				if ($bed && $bed.length) $bed.addClass('ax-bed--busy');
				frappe.call({
					method: 'apex_habitat.habitat.api.front_desk.quick_check_out',
					args: {
						bed,
						checkout_date: values.checkout_date,
						checkout_reason: values.checkout_reason,
						room_condition_snapshot: values.room_condition_snapshot || null,
					},
					callback: (r) => {
						if (r.exc || !r.message) {
							if ($bed && $bed.length) $bed.removeClass('ax-bed--busy');
							return;
						}
						if (r.message.requires_full_form) {
							if ($bed && $bed.length) $bed.removeClass('ax-bed--busy');
							frappe.show_alert({
								message: __('This resident has custody items. Opening the full Checkout form to clear custody.'),
								indicator: 'orange',
							});
							frappe.new_doc('Accommodation Checkout', { assignment: r.message.assignment });
							return;
						}
						frappe.show_alert({ message: __('Checked out: {0}', [r.message.checkout]), indicator: 'green' });
						this.refresh();
					},
					error: () => {
						if ($bed && $bed.length) $bed.removeClass('ax-bed--busy');
					},
				});
			},
		});
		d.show();
	}

	_house_in_bed(bed, $bed) {
		const worker = this.active;
		// Optimistic: the clicked bed turns red with a per-bed spinner immediately —
		// no full-screen freeze + grid refetch. Reconciled from the reply, rolled back on exc.
		if ($bed && $bed.length) {
			$bed.removeClass('ax-bed--green').addClass('ax-bed--red ax-bed--busy').removeAttr('tabindex role');
		}
		const rollback = () => {
			if ($bed && $bed.length) {
				$bed.removeClass('ax-bed--red ax-bed--busy').addClass('ax-bed--green').attr({ tabindex: 0, role: 'button' });
			}
		};
		frappe.call({
			method: 'apex_habitat.habitat.api.front_desk.quick_check_in',
			args: {
				bed,
				party_type: worker.party_type,
				party: worker.party,
				project: this.project,
				check_in_date: frappe.datetime.get_today(),
			},
			callback: (r) => {
				if (r.exc || !r.message) {
					rollback();
					return;
				}
				if ($bed && $bed.length) $bed.removeClass('ax-bed--busy'); // reconciled: stays red
				frappe.show_alert({ message: __('Housed {0}', [worker.label]), indicator: 'green' });
				// [#dvlqkx]
				const dupe = this.cart.some(
					(c) => c.party === worker.party && c.party_type === worker.party_type
				);
				if (!dupe) this.cart.push({ ...worker, bed: r.message.bed || bed });
				this.active = null;
				this.$active.empty();
				this._render_cart();
				// Reconcile counts/capacity/stages from the LOCAL grid model — no grid
				// refetch (which would skeleton-reload the whole floor under the user).
				this._reconcile_housed_bed(bed, worker, $bed);
			},
			error: () => rollback(),
		});
	}

	// Mutate the in-memory grid for a just-housed bed and re-render only the
	// capacity meter + stepper — the floor DOM (with the now-red bed) is untouched.
	_reconcile_housed_bed(bed, worker, $bed) {
		if (!this.grid) return;
		const s = this.grid.summary || (this.grid.summary = {});
		if (s.available) s.available -= 1;
		s.occupied = (s.occupied || 0) + 1;
		(this.grid.floors || []).forEach((floor) =>
			(floor.rooms || []).forEach((room) =>
				(room.beds || []).forEach((b) => {
					if (b.bed === bed) {
						b.bed_color = 'red';
						b.occupant = { employee_name: worker.label, party_type: worker.party_type, party: worker.party };
					}
				})
			)
		);
		// Surface the occupant name in the existing bed without a full grid repaint.
		if ($bed && $bed.length && !$bed.find('.ax-bed-occupant').length) {
			$('<span class="ax-bed-occupant"></span>').text(worker.label || '').appendTo($bed);
		}
		this._render_capacity(this.grid);
		this._render_stages();
		this._load_manifest(); // a housed arrival may tick its manifest line
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
			const dots = this._cart_dots(c);
			const $item = $(`<div class="ax-cart-item${dots.complete ? ' ax-cart-item--done' : ''}"></div>`)
				.html(
					`<span class="ax-cart-name">${frappe.utils.escape_html(c.label || c.party)}</span>` +
						`<span class="ax-cart-bed text-muted"><bdi>${frappe.utils.escape_html(c.bed || '')}</bdi></span>`
				)
				.appendTo($list);
			$('<div class="ax-cart-dots"></div>').html(dots.html).appendTo($item);
			// [#smadir]
			$('<button class="btn btn-xs btn-link ax-cart-checkin"></button>')
				.text(__('Check-in slip'))
				.on('click', () => this._print_checkin(c))
				.appendTo($item);
		});
	}

	// Per-worker completion dots from existing client state. Custody/Card apply only
	// to an Employee (a Temporary Worker defers both), so its pack is Housed+Transport.
	_cart_dots(c) {
		const is_emp = c.party_type === 'Employee';
		const housed = true; // in the cart means already housed this session
		const custody = is_emp ? !!c._custody_issue : null; // null = not applicable
		const card = is_emp ? !!c._card_done : null;
		const transport = !!this.transportStarted;
		const dot = (label, state) => {
			// state: true=done, false=pending, null=not applicable (shows an en-dash)
			const mark = state === null ? '–' : state ? '✓' : '–';
			const cls = state === null ? 'na' : state ? 'on' : 'off';
			return `<span class="ax-cart-dot ax-cart-dot--${cls}">${frappe.utils.escape_html(label)} ${mark}</span>`;
		};
		const html =
			dot(__('Housed'), housed) +
			dot(__('Custody'), custody) +
			dot(__('Card'), card) +
			dot(__('Transport'), transport);
		// Complete = every APPLICABLE step done (null steps are not required).
		const complete = housed && (custody !== false) && (card !== false) && transport;
		return { html, complete };
	}

	// [#33np9k]
	_render_deck() {
		this.$deck.empty();
		this._render_stages();
		if (!this.cart.length) return;
		if (this.catalog == null) this._load_catalog();
		const $cust = $('<section class="ax-deck-sec" data-stage-target="custody"></section>').appendTo(this.$deck);
		$('<header class="ax-deck-head"></header>').text(__('Custody Handover')).appendTo($cust);
		if (this.catalogError) {
			// Catalog load failed → inline retry, not an empty store with broken selects.
			const $err = $('<div class="ax-catalog-error"></div>').appendTo($cust);
			$('<span></span>').text(__("Couldn't load custody store — retry")).appendTo($err);
			$('<button class="btn btn-xs btn-default ax-catalog-retry"></button>')
				.text(__('Retry'))
				.on('click', () => this._retry_catalog())
				.appendTo($err);
		}
		const $list = $('<div class="ax-deck-list"></div>').appendTo($cust);
		this.cart.forEach((c) => this._custody_row($list, c));
		// [#gk3q62]
		const $card = $('<section class="ax-deck-sec" data-stage-target="card"></section>').appendTo(this.$deck);
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
		this.catalogError = false;
		if (!this.building) return;
		frappe
			.call({
				method: 'apex_habitat.habitat.api.custody_kiosk.get_kiosk_catalog',
				args: { building: this.building },
			})
			.then((r) => {
				this.catalog = (r.message && r.message.articles) || [];
				this.catalogError = false;
				if (this.cart.length) this._render_deck(); // refill the selects now the catalog is in
			})
			.catch(() => {
				// Surface a retry affordance in the deck instead of a silent empty <select>.
				this.catalog = [];
				this.catalogError = true;
				if (this.cart.length) this._render_deck();
			});
	}

	// Reload the custody store on demand (catalog-load failure recovery).
	_retry_catalog() {
		this.catalog = null;
		this.catalogError = false;
		this._load_catalog();
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
		const targets = this.cart.filter((c) => c.party_type === 'Employee' && !c._card_done);
		if (!targets.length) return;
		// Per-row pending state instead of a full-screen freeze: each QR row shows a
		// spinner now, then flips to its done (QR + link) state on the reply.
		targets.forEach((c) => (c._card_pending = true));
		this._render_qr_block();
		frappe.call({
			method: 'apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token.batch_issue_worker_links',
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
					// Pending: a spinner + label, not nothing-until-it-appears.
					$('<div class="ax-qr-pending"></div>')
						.html(`<span class="ax-qr-spinner" aria-hidden="true"></span>`)
						.append(document.createTextNode(__('Creating QR…')))
						.appendTo($item);
					return;
				}
				const m = c._card_qr;
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
		const free = s.available || 0;
		const occupied = s.occupied || 0;
		const total = s.total_beds || 0;
		// One occupancy meter instead of three loose numbers: green fill = free,
		// red = occupied, dashed = over-capacity (occupied beyond physical total).
		// Widths are shares of the running denominator so every segment stays visible.
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
		$('<div class="ax-cap-legend ax-cap-legend--free"></div>')
			.text(__('{0} free', [free]))
			.appendTo($cap);
		$('<div class="ax-cap-legend ax-cap-legend--occ"></div>')
			.text(__('{0} occupied', [occupied]))
			.appendTo($cap);
		if (over) {
			$('<div class="ax-cap-legend ax-cap-legend--over"></div>')
				.text(__('{0} over capacity', [over]))
				.appendTo($cap);
		}
		this.$capacity.empty().append($cap);
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
		// Numbered stepper (the step index is drawn by a CSS counter, not text).
		this.$stages.empty().attr('role', 'list');
		chips.forEach(([k, label, done], i) => {
			const state = done ? 'done' : i === firstTodo ? 'now' : 'todo';
			const $step = $(
				`<button type="button" class="ax-step ax-step--${state}" data-stage="${k}" role="listitem"></button>`
			);
			$('<span class="ax-step-label"></span>').text(label).appendTo($step);
			// A completed step jumps to its Actions-deck section so the stepper navigates.
			if (done) {
				$step.on('click', () => this._scroll_to_stage(k));
			} else {
				$step.prop('disabled', true);
			}
			this.$stages.append($step);
		});
	}

	// Scroll the deck section for a completed stage into view (no JS dep — native).
	_scroll_to_stage(stage) {
		const el = this.$deck && this.$deck.find(`[data-stage-target="${stage}"]`).get(0);
		if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
	}

	_render_grid(grid) {
		this._render_capacity(grid);
		this._render_stages();
		const summary = (grid && grid.summary) || {};
		if (!grid || !(grid.floors || []).length) {
			// Two distinct empty states: rooms with beds all taken vs no rooms yet.
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
						`<section class="ax-floor-group"><header class="ax-floor-header">` +
						`${frappe.utils.escape_html(floor.floor_label || '')}</header>` +
						`<div class="ax-rooms">${rooms}</div></section>`
					);
				})
				.join('')
		);
		// Beds render but none are free → tell the user to use Over-capacity (no generic blank).
		if (summary.total_beds > 0 && !summary.available) {
			$('<div class="ax-floor-banner"></div>')
				.text(__('This building has rooms but every bed is occupied — use Over-capacity'))
				.prependTo(this.$floor);
		}
	}

	_room_html(room) {
		// Pass the room readiness so an amber bed can name its blocker (server-driven).
		const beds = (room.beds || []).map((bed) => this._bed_html(bed, room.readiness_status)).join('');
		const occ = `${room.current_occupancy || 0}/${room.bed_capacity || 0}`;
		// Tint/badge a room that already holds the selected worker's project (server-driven
		// dominant_project; read-only — no client recompute).
		const sameProject = !!(this.project && room.dominant_project && room.dominant_project === this.project);
		const projClass = sameProject ? ' ax-room--same-project' : '';
		const projBadge = sameProject
			? `<span class="ax-room-proj" title="${__('Same project as the selected worker')}">${__('Same project')}</span>`
			: '';
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
			`<div class="ax-room${projClass}"><div class="ax-room-header">` +
			`<span class="ax-room-number">${frappe.utils.escape_html(room.room_number || room.room || '')}${projBadge}</span>` +
			`<span class="ax-room-meta">${occ}${readiness}</span></div>` +
			`<div class="ax-beds">${beds}</div>${oc}</div>`
		);
	}

	_bed_html(bed, readiness_status) {
		const color = bed.bed_color || 'grey'; // server-computed; never recomputed here
		const temp = bed.is_temporary ? ' ax-bed--temp' : ''; // virtual over-capacity bed
		// Green (house) and red (check out) beds are both actionable and keyboard-reachable.
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
		// Amber beds name the readiness blocker (room-level) instead of leaving it implicit.
		const blocker =
			color === 'amber' && readiness_status && readiness_status !== 'Ready' && readiness_status !== 'Unknown'
				? `<span class="ax-bed-blocker">${frappe.utils.escape_html(__(readiness_status))}</span>`
				: '';
		// Explicit Temp chip on over-capacity beds, not just the dashed border.
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
