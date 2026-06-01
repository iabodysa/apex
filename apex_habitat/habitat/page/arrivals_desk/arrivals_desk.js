// Arrivals Desk — "Anchor / Floor / Cart" single-screen worker check-in.
//
// Batch 1 (this file): the page shell + building ANCHOR (Zone A) + stage progress
// strip (Zone B) + a READ-ONLY rooms/beds floor-map (Zone C), reusing the Front
// Desk get_building_grid reader verbatim. The right rail (worker search, the
// arrivals cart, custody handover, arrival card and transport) plus every write
// land in later batches. Frappe desk library only; the AFMCO brand lives in the
// scoped arrivals_desk.css.

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
		this.grid = null;
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
		this._render_stages(false);
		// Body: floor-map (left) + reserved right rail (filled in later batches).
		this.$body = $('<div class="ax-body"></div>').appendTo(this.$root);
		this.$floor = $('<div class="ax-floor"></div>').appendTo(this.$body);
		this.$rail = $('<aside class="ax-rail"></aside>').appendTo(this.$body);
		this.$rail.html(
			`<div class="ax-rail-placeholder text-muted">${frappe.utils.escape_html(
				__('Worker search, the arrivals cart and custody come in the next steps.')
			)}</div>`
		);
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
					this._render_stages(false);
					this._render_capacity(null);
					this._render_empty(__('Pick a building to start the arrival.'));
				}
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

	_render_stages(building_done) {
		const chips = [
			['building', __('Building'), building_done],
			['housed', __('Housed'), false],
			['custody', __('Custody'), false],
			['card', __('Card'), false],
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
		this._render_stages(true);
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
		return (
			`<div class="ax-room"><div class="ax-room-header">` +
			`<span class="ax-room-number">${frappe.utils.escape_html(room.room_number || room.room || '')}</span>` +
			`<span class="ax-room-meta">${occ}${readiness}</span></div>` +
			`<div class="ax-beds">${beds}</div></div>`
		);
	}

	_bed_html(bed) {
		const color = bed.bed_color || 'grey';
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
			`<div class="ax-bed ax-bed--${color}" data-bed="${frappe.utils.escape_html(bed.bed || '')}" ` +
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
