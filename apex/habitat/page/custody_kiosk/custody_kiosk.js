// Copyright (c) 2026, AFMCO and contributors
// [#qt2p0p]

frappe.pages["custody-kiosk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Custody Kiosk"),
		single_column: true,
	});

	const kiosk = new CustodyKiosk(page);
	kiosk.setup();
};

// Kiosk look restored on native Desk CSS variables — a Desk page ships no stylesheet,
// so the removed custody_kiosk.css is re-expressed as inline style="" overlays bound
// to Desk vars (theme + dark-mode aware) with logical properties (RTL-mirrored). No
// <style> injection (T-680).
const CK_STYLE = {
	modebar:
		"display:inline-flex;gap:0;margin-block:4px 12px;border:1px solid var(--border-color);border-radius:8px;overflow:hidden;background:var(--control-bg);",
	mode_btn:
		"appearance:none;border:none;background:transparent;color:var(--text-color);font-size:14px;font-weight:600;padding-block:8px;padding-inline:22px;cursor:pointer;min-inline-size:96px;",
	mode_btn_divider: "border-inline-start:1px solid var(--border-color);",
	mode_btn_active: "background:var(--primary);color:var(--text-on-blue);",
	// flex-wrap lets the sticky cart drop under the catalog on a narrow viewport
	// (replaces the removed max-width column media query).
	layout: "display:flex;gap:16px;align-items:flex-start;padding-block:8px 32px;padding-inline:4px;flex-wrap:wrap;",
	catalog: "flex:1 1 320px;min-inline-size:0;",
	tools: "margin-block-end:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;",
	search: "max-inline-size:360px;font-size:15px;",
	empty: "padding-block:48px;padding-inline:16px;text-align:center;font-size:15px;",
	tiles: "display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px;",
	tile:
		"border:2px solid var(--border-color);border-radius:10px;padding:12px;background:var(--card-bg);cursor:pointer;user-select:none;display:flex;flex-direction:column;gap:8px;min-block-size:180px;",
	tile_skeleton: "cursor:default;pointer-events:none;",
	thumb:
		"inline-size:100%;block-size:110px;border-radius:8px;overflow:hidden;background:var(--control-bg);display:flex;align-items:center;justify-content:center;",
	thumb_img: "inline-size:100%;block-size:100%;object-fit:cover;",
	initials: "font-size:34px;font-weight:700;color:var(--text-muted);",
	tile_name: "font-weight:600;font-size:14px;line-height:1.3;",
	tile_meta: "font-size:12px;color:var(--text-muted);",
	tile_sub: "font-size:11px;margin-block-start:-2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	skel_thumb: "inline-size:100%;block-size:110px;border-radius:8px;background:var(--skeleton-bg);",
	skel_line: "block-size:12px;inline-size:80%;border-radius:6px;background:var(--skeleton-bg);",
	skel_line_sm: "block-size:12px;inline-size:50%;border-radius:6px;background:var(--skeleton-bg);",
	cart:
		"flex:0 0 320px;border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg);display:flex;flex-direction:column;position:sticky;inset-block-start:8px;max-block-size:calc(100vh - 120px);",
	cart_header: "padding-block:14px;padding-inline:16px;font-size:16px;font-weight:600;border-block-end:1px solid var(--border-color);",
	cart_lines: "flex:1 1 auto;overflow-y:auto;padding-block:8px;",
	cart_empty: "padding-block:32px;padding-inline:16px;text-align:center;font-size:14px;",
	cart_line:
		"display:flex;align-items:center;justify-content:space-between;gap:10px;padding-block:10px;padding-inline:16px;border-block-end:1px solid var(--border-color);",
	cart_line_name: "font-size:14px;font-weight:500;flex:1 1 auto;min-inline-size:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	cart_line_info: "flex:1 1 auto;min-inline-size:0;",
	// name inside the return-cart info stack: no flex-grow (overridden from base).
	cart_line_name_info: "font-size:14px;font-weight:500;flex:0 0 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	cart_line_sub: "font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	stepper: "display:flex;align-items:center;gap:8px;flex:0 0 auto;",
	step: "inline-size:36px;block-size:36px;font-size:18px;line-height:1;padding:0;font-weight:700;",
	step_qty: "min-inline-size:28px;text-align:center;font-size:15px;font-weight:600;",
	cart_footer: "padding-block:14px;padding-inline:16px;border-block-start:1px solid var(--border-color);",
	cart_subtotal: "display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-block-end:12px;font-size:14px;",
	subtotal_value: "font-size:18px;font-weight:700;",
	action_btn: "inline-size:100%;",
	error:
		"grid-column:1 / -1;padding-block:40px;padding-inline:16px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:12px;",
	error_msg: "font-size:15px;",
};

class CustodyKiosk {
	constructor(page) {
		this.page = page;
		// [#mode01]
		this.mode = "issue";
		// Recipient (both modes) — party_type/party Dynamic Link pair.
		this.party_type = "Employee";
		this.party = null;
		// Issue-mode state
		this.building = null;
		this.articles = [];
		// Return-mode state
		this.held = [];
		// [#kwkz4i]
		this.cart = {};
		this.return_cart = {};
	}

	setup() {
		this._setup_controls();
		this._build_layout();
		this._apply_mode();
	}

	_setup_controls() {
		// [#party01] — the recipient is a party_type/party pair (Employee |
		// Temporary Worker) matching the Custody Issue Dynamic Link; it selects
		// the issue recipient and the return holder in both modes.
		this.party_type_field = this.page.add_field({
			fieldname: "party_type",
			label: __("Worker Type"),
			fieldtype: "Select",
			options: ["Employee", "Temporary Worker"],
			default: "Employee",
			change: () => {
				const val = this.party_type_field.get_value() || "Employee";
				if (val !== this.party_type) {
					this.party_type = val;
					this.party = null;
					this.party_field.set_value("");
					this._update_party_options();
					this.return_cart = {};
					if (this.mode === "return") {
						this._render_held_empty(
							__("Select a worker to load held custody.")
						);
					}
					this._render_cart();
				}
			},
		});

		this.party_field = this.page.add_field({
			fieldname: "party",
			label: __("Worker"),
			fieldtype: "Link",
			options: "Employee",
			change: () => {
				const val = this.party_field.get_value() || null;
				if (val !== this.party) {
					this.party = val;
					// Return mode reloads the holder's returnable custody; issue
					// mode's catalog depends on building, not party.
					if (this.mode === "return") {
						this.return_cart = {};
						this.refresh();
					}
				}
			},
		});

		this.building_field = this.page.add_field({
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
			change: () => {
				const val = this.building_field.get_value() || null;
				if (val !== this.building) {
					this.building = val;
					this.refresh();
				}
			},
		});

		// [#scan01] — one scan box accelerates both modes: a worker-badge scan sets
		// the party, an article-barcode scan adds the tile to the cart. A HID/USB
		// scanner types the code + Enter (Data field fires `change`); the box keeps
		// focus so successive scans need no click. This is the only Desk scan input —
		// camera scanning is a mobile-portal feature, not a Desk page.
		this.scan_field = this.page.add_field({
			fieldname: "scan",
			label: __("Scan"),
			fieldtype: "Data",
			description: __("Scan a worker badge or an article barcode"),
			change: () => this._handle_scan(this.scan_field.get_value()),
		});

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	// [#scan02] — route one scanned token via the server resolver, then clear and
	// refocus the box for the next scan. The resolver classifies the token; the
	// client only dispatches the result so issue/return logic stays one source.
	_handle_scan(raw) {
		const code = (raw || "").trim();
		// Clear immediately so a scanner's trailing Enter can't double-fire and the
		// box is ready for the next badge/barcode.
		this.scan_field.set_value("");
		if (!code) return;
		frappe.call({
			method: "apex.habitat.api.custody_kiosk.resolve_scan",
			args: { code: code, party_type: this.party_type, building: this.building },
			callback: (r) => {
				const res = r.message || {};
				if (res.kind === "worker") {
					this._apply_worker_scan(res);
				} else if (res.kind === "article") {
					this._apply_article_scan(res.article);
				} else {
					frappe.show_alert({
						message: __("No worker or article matched: {0}", [code]),
						indicator: "orange",
					});
				}
				this._focus_scan();
			},
			error: () => {
				frappe.show_alert({
					message: __("Could not resolve the scan. Please try again."),
					indicator: "red",
				});
				this._focus_scan();
			},
		});
	}

	// [#scan03] — a worker badge sets the party; if the badge belongs to the other
	// party kind the resolver returns it, so flip the selector to match. Setting the
	// party field drives the same `change` path a manual pick does (return mode
	// reloads held custody).
	_apply_worker_scan(res) {
		if (res.party_type && res.party_type !== this.party_type) {
			this.party_type = res.party_type;
			this.party_type_field.set_value(res.party_type);
			this._update_party_options();
		}
		this.party = res.party;
		this.party_field.set_value(res.party);
		frappe.show_alert({
			message: __("Worker set: {0}", [res.party_name || res.party]),
			indicator: "green",
		});
		if (this.mode === "return") {
			this.return_cart = {};
			this.refresh();
		}
	}

	// [#scan04] — an article barcode adds the tile to the active cart. Issue mode
	// adds straight to the cart (one unit, like a tile tap). Return mode can only
	// return what is held, so match the scan against the loaded held lines and add
	// that line; otherwise hint that the worker does not hold it.
	_apply_article_scan(art) {
		if (!art || !art.article) return;
		if (this.mode === "return") {
			const line = (this.held || []).find((l) => l.article === art.article);
			if (line) {
				this._add_held_to_cart(line);
				frappe.show_alert({
					message: __("Added to return: {0}", [line.article_name || line.article]),
					indicator: "green",
				});
			} else {
				frappe.show_alert({
					message: __("This worker does not hold: {0}", [art.article_name || art.article]),
					indicator: "orange",
				});
			}
			return;
		}
		this._add_to_cart(art);
		frappe.show_alert({
			message: __("Added: {0}", [art.article_name || art.article]),
			indicator: "green",
		});
	}

	_focus_scan() {
		if (this.scan_field && this.scan_field.$input) {
			this.scan_field.$input.focus();
		}
	}

	_update_party_options() {
		// [#party02]
		const target = this.party_type === "Temporary Worker" ? "Temporary Worker" : "Employee";
		this.party_field.df.options = target;
		this.party_field.set_value("");
	}

	_build_layout() {
		this.$layout = $('<div class="ck-layout"></div>').attr("style", CK_STYLE.layout).appendTo(this.page.main);

		// [#modeui]
		const $modebar = $(
			`<div class="ck-modebar" role="tablist" aria-label="${frappe.utils.escape_html(
				__("Issue or return mode")
			)}"></div>`
		)
			.attr("style", CK_STYLE.modebar)
			.appendTo(this.page.main);
		// Mode bar must sit ABOVE the catalog/cart layout.
		$modebar.insertBefore(this.$layout);

		this.$mode_issue = $(
			`<button class="ck-mode-btn" role="tab" type="button"></button>`
		)
			.attr("style", CK_STYLE.mode_btn)
			.text(__("Issue Custody"))
			.appendTo($modebar)
			.on("click", () => this._set_mode("issue"));
		this.$mode_return = $(
			`<button class="ck-mode-btn" role="tab" type="button"></button>`
		)
			.attr("style", CK_STYLE.mode_btn + CK_STYLE.mode_btn_divider)
			.text(__("Return"))
			.appendTo($modebar)
			.on("click", () => this._set_mode("return"));

		// [#20cz3t]
		const $catalog = $('<div class="ck-catalog"></div>').attr("style", CK_STYLE.catalog).appendTo(this.$layout);
		const $tools = $('<div class="ck-tools"></div>').attr("style", CK_STYLE.tools).appendTo($catalog);
		this.$search = $(
			`<input type="search" class="ck-search form-control" placeholder="${frappe.utils.escape_html(
				__("Search articles…")
			)}" aria-label="${frappe.utils.escape_html(__("Search articles"))}">`
		)
			.attr("style", CK_STYLE.search)
			.appendTo($tools);
		// [#guxhpt]
		const debounced_render = frappe.utils.debounce(() => this._render_visible(), 120);
		this.$search.on("input", debounced_render);

		this.$tiles = $('<div class="ck-tiles"></div>').attr("style", CK_STYLE.tiles).appendTo($catalog);

		// [#4232vl]
		const $cart = $('<div class="ck-cart"></div>').attr("style", CK_STYLE.cart).appendTo(this.$layout);
		this.$cart_header = $('<div class="ck-cart-header"></div>')
			.attr("style", CK_STYLE.cart_header)
			.text(__("Cart"))
			.appendTo($cart);
		this.$cart_lines = $('<div class="ck-cart-lines"></div>').attr("style", CK_STYLE.cart_lines).appendTo($cart);
		const $footer = $('<div class="ck-cart-footer"></div>').attr("style", CK_STYLE.cart_footer).appendTo($cart);
		// Value subtotal sits above the action button; aria-live so screen
		// readers announce the running total as items are added/removed.
		this.$subtotal = $(
			`<div class="ck-cart-subtotal" role="status" aria-live="polite"></div>`
		)
			.attr("style", CK_STYLE.cart_subtotal)
			.appendTo($footer);
		this.$action_btn = $(
			`<button class="btn btn-primary btn-lg ck-action-btn"></button>`
		)
			.attr("style", CK_STYLE.action_btn)
			.text(__("Issue"))
			.appendTo($footer);
		this.$action_btn.on("click", () => this._commit());
	}

	// [#modeset]
	_set_mode(mode) {
		if (mode === this.mode) return;
		this.mode = mode;
		this._apply_mode();
	}

	_apply_mode() {
		const is_return = this.mode === "return";

		// Toggle the tablist visual + ARIA state (aria-pressed for a toggle pair).
		// The active fill is re-applied inline since there is no stylesheet to key
		// the `.active` class off of.
		this.$mode_issue
			.toggleClass("active", !is_return)
			.attr("style", CK_STYLE.mode_btn + (!is_return ? CK_STYLE.mode_btn_active : ""))
			.attr("aria-pressed", String(!is_return))
			.attr("aria-selected", String(!is_return));
		this.$mode_return
			.toggleClass("active", is_return)
			.attr("style", CK_STYLE.mode_btn + CK_STYLE.mode_btn_divider + (is_return ? CK_STYLE.mode_btn_active : ""))
			.attr("aria-pressed", String(is_return))
			.attr("aria-selected", String(is_return));

		// The party_type/party pair selects the recipient in BOTH modes (issue
		// recipient / return holder); the building store is an issue-only field.
		this._toggle_field(this.party_type_field, true);
		this._toggle_field(this.party_field, true);
		this._toggle_field(this.building_field, !is_return);

		// The catalog search filters articles in both modes.
		this.$cart_header.text(is_return ? __("Return cart") : __("Cart"));
		this.$action_btn.text(is_return ? __("Return") : __("Issue"));

		if (is_return) {
			if (!this.party) {
				this._render_held_empty(__("Select a worker to load held custody."));
			} else {
				this.refresh();
			}
		} else {
			if (!this.building) {
				this._render_empty(__("Select a building to load the catalog."));
			} else {
				this._render_tiles();
			}
		}
		this._render_cart();
	}

	_toggle_field(field, show) {
		if (!field || !field.$wrapper) return;
		field.$wrapper.toggle(!!show);
	}

	refresh() {
		if (this.mode === "return") {
			this._refresh_held();
			return;
		}
		if (!this.building) {
			this._render_empty(__("Select a building to load the catalog."));
			return;
		}
		this._render_loading();
		frappe.call({
			method: "apex.habitat.api.custody_kiosk.get_kiosk_catalog",
			args: { building: this.building },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._render_error(__("Could not load the catalog."), () => this.refresh());
					return;
				}
				this.articles = r.message.articles || [];
				this._render_tiles();
			},
			error: () => {
				this._render_error(__("Could not load the catalog."), () => this.refresh());
			},
		});
	}

	// [#heldload]
	_refresh_held() {
		if (!this.party) {
			this._render_held_empty(__("Select a worker to load held custody."));
			return;
		}
		this._render_loading();
		frappe.call({
			method: "apex.habitat.api.custody_kiosk.get_party_custody",
			args: { party_type: this.party_type, party: this.party },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._render_error(__("Could not load held custody."), () => this.refresh());
					return;
				}
				this.held = r.message.lines || [];
				this._render_held();
			},
			error: () => {
				this._render_error(__("Could not load held custody."), () => this.refresh());
			},
		});
	}

	_render_visible() {
		if (this.mode === "return") {
			this._render_held();
		} else {
			this._render_tiles();
		}
	}

	_render_empty(message) {
		this.$tiles.empty();
		$('<div class="ck-empty text-muted"></div>').attr("style", CK_STYLE.empty).text(message).appendTo(this.$tiles);
	}

	_render_held_empty(message) {
		this.held = [];
		this._render_empty(message);
	}

	_render_loading() {
		this.$tiles.empty();
		// [#3omcm3] — flat placeholder blocks on the native --skeleton-bg Desk var
		// (theme + dark aware); the removed shimmer @keyframes needs a stylesheet.
		for (let i = 0; i < 6; i++) {
			const $sk = $('<div class="ck-tile ck-tile-skeleton" aria-hidden="true"></div>').attr(
				"style",
				CK_STYLE.tile + CK_STYLE.tile_skeleton
			);
			$('<div class="ck-tile-thumb ck-skel"></div>').attr("style", CK_STYLE.skel_thumb).appendTo($sk);
			$('<div class="ck-skel ck-skel-line"></div>').attr("style", CK_STYLE.skel_line).appendTo($sk);
			$('<div class="ck-skel ck-skel-line ck-skel-line-sm"></div>').attr("style", CK_STYLE.skel_line_sm).appendTo($sk);
			$sk.appendTo(this.$tiles);
		}
	}

	_render_error(message, retry) {
		this.$tiles.empty();
		const $box = $('<div class="ck-error"></div>').attr("style", CK_STYLE.error).appendTo(this.$tiles);
		$('<div class="ck-error-msg text-danger"></div>').attr("style", CK_STYLE.error_msg).text(message).appendTo($box);
		$('<button class="btn btn-default btn-sm ck-retry"></button>')
			.text(__("Retry"))
			.appendTo($box)
			.on("click", () => retry());
	}

	_render_tiles() {
		this.$tiles.empty();
		const term = (this.$search.val() || "").trim().toLowerCase();
		const list = this.articles.filter((a) => {
			if (!term) return true;
			return (a.article_name || "").toLowerCase().indexOf(term) !== -1;
		});

		if (!list.length) {
			this._render_empty(__("No articles found."));
			return;
		}

		list.forEach((art) => {
			this._render_tile(art).appendTo(this.$tiles);
		});
	}

	// [#heldtiles]
	_render_held() {
		this.$tiles.empty();
		const term = (this.$search.val() || "").trim().toLowerCase();
		const list = this.held.filter((l) => {
			if (!term) return true;
			return (l.article_name || "").toLowerCase().indexOf(term) !== -1;
		});

		if (!list.length) {
			this._render_empty(
				this.held.length
					? __("No articles found.")
					: __("This worker holds no returnable custody.")
			);
			return;
		}

		list.forEach((line) => {
			this._render_held_tile(line).appendTo(this.$tiles);
		});
	}

	_render_tile(art) {
		const $tile = $(`<div class="ck-tile" tabindex="0" role="button"></div>`).attr("style", CK_STYLE.tile);

		const $thumb = $('<div class="ck-tile-thumb"></div>').attr("style", CK_STYLE.thumb).appendTo($tile);
		if (art.image) {
			$('<img class="ck-tile-img">')
				.attr("style", CK_STYLE.thumb_img)
				.attr("src", art.image)
				.attr("alt", art.article_name || art.article)
				.appendTo($thumb);
		} else {
			$('<div class="ck-tile-initials"></div>')
				.attr("style", CK_STYLE.initials)
				.text(this._initials(art.article_name || art.article))
				.appendTo($thumb);
		}

		$('<div class="ck-tile-name"></div>')
			.attr("style", CK_STYLE.tile_name)
			.text(art.article_name || art.article)
			.appendTo($tile);

		// UOM + in-stock count. The count is bidi-isolated in <bdi> and the
		// number formatted via Frappe format_number, so an Arabic label never
		// shares one bidi run with a Latin/grouped number.
		const $meta = this._render_tile_meta(art.uom, art.store_balance);
		if ($meta) $meta.appendTo($tile);

		const add = () => this._add_to_cart(art);
		$tile.on("click", add);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				add();
			}
		});
		return $tile;
	}

	// [#heldtile]
	_render_held_tile(line) {
		const $tile = $(`<div class="ck-tile" tabindex="0" role="button"></div>`).attr("style", CK_STYLE.tile);

		const $thumb = $('<div class="ck-tile-thumb"></div>').attr("style", CK_STYLE.thumb).appendTo($tile);
		$('<div class="ck-tile-initials"></div>')
			.attr("style", CK_STYLE.initials)
			.text(this._initials(line.article_name || line.article))
			.appendTo($thumb);

		$('<div class="ck-tile-name"></div>')
			.attr("style", CK_STYLE.tile_name)
			.text(line.article_name || line.article)
			.appendTo($tile);

		const $meta = this._render_tile_meta(line.uom, line.qty, __("Held: {0}"));
		if ($meta) $meta.appendTo($tile);

		// Each held line is tied to its source Custody Issue (bidi-isolated).
		const $sub = $('<div class="ck-tile-sub text-muted"></div>').attr("style", CK_STYLE.tile_sub).appendTo($tile);
		const [isub_before, isub_after] = __("Issue: {0}").split("{0}");
		$("<span></span>").text(isub_before).appendTo($sub);
		$("<bdi></bdi>").text(line.custody_issue).appendTo($sub);
		if (isub_after !== undefined) $("<span></span>").text(isub_after).appendTo($sub);

		const add = () => this._add_held_to_cart(line);
		$tile.on("click", add);
		$tile.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				add();
			}
		});
		return $tile;
	}

	_initials(name) {
		const parts = String(name || "")
			.trim()
			.split(/\s+/)
			.slice(0, 2);
		return parts.map((p) => p.charAt(0).toUpperCase()).join("") || "?";
	}

	// Build a tile meta line "UOM · <label with bdi-isolated count>". The count is
	// formatted via Frappe format_number (Arabic-build digit grouping) and the
	// {0} slot of the translated label is filled with a real <bdi> node, so the
	// Arabic label + Latin number never share a bidi run. `template` is a
	// translated format-string carrying one {0}. Returns a node or null.
	_render_tile_meta(uom, count, template) {
		const has_count = count !== null && count !== undefined;
		if (!uom && !has_count) return null;
		const $meta = $('<div class="ck-tile-meta"></div>').attr("style", CK_STYLE.tile_meta);
		if (uom) $("<span></span>").text(uom).appendTo($meta);
		if (has_count) {
			if (uom) $("<span></span>").text(" · ").appendTo($meta);
			const tmpl = template || __("In stock: {0}");
			const [before, after] = tmpl.split("{0}");
			$("<span></span>").text(before).appendTo($meta);
			$("<bdi></bdi>").text(format_number(flt(count))).appendTo($meta);
			if (after !== undefined) $("<span></span>").text(after).appendTo($meta);
		}
		return $meta;
	}

	_add_to_cart(art) {
		const existing = this.cart[art.article];
		if (existing) {
			existing.qty += 1;
		} else {
			this.cart[art.article] = {
				article: art.article,
				article_name: art.article_name || art.article,
				uom: art.uom,
				// Unit cost drives the cart value subtotal; may be 0/undefined.
				rate: flt(art.standard_unit_cost),
				qty: 1,
			};
		}
		this._render_cart();
	}

	// [#heldadd]
	_add_held_to_cart(line) {
		const key = `${line.custody_issue}::${line.article}`;
		const existing = this.return_cart[key];
		if (existing) {
			// Never let the return cart exceed the held quantity.
			if (existing.qty < line.qty) existing.qty += 1;
		} else {
			this.return_cart[key] = {
				key: key,
				custody_issue: line.custody_issue,
				article: line.article,
				article_name: line.article_name || line.article,
				uom: line.uom,
				qty: 1,
				max: line.qty,
			};
		}
		this._render_cart();
	}

	_change_qty(article, delta) {
		const line = this.cart[article];
		if (!line) return;
		line.qty += delta;
		if (line.qty <= 0) {
			delete this.cart[article];
		}
		this._render_cart();
	}

	// [#heldqty]
	_change_return_qty(key, delta) {
		const line = this.return_cart[key];
		if (!line) return;
		line.qty += delta;
		if (line.qty <= 0) {
			delete this.return_cart[key];
		} else if (line.max && line.qty > line.max) {
			line.qty = line.max;
		}
		this._render_cart();
	}

	_render_cart() {
		if (this.mode === "return") {
			this._render_return_cart();
			return;
		}
		this.$cart_lines.empty();
		const lines = Object.values(this.cart);

		if (!lines.length) {
			$('<div class="ck-cart-empty text-muted"></div>')
				.attr("style", CK_STYLE.cart_empty)
				.text(__("Cart is empty."))
				.appendTo(this.$cart_lines);
			this.$action_btn.prop("disabled", true);
			this._render_subtotal(0);
			return;
		}

		this.$action_btn.prop("disabled", false);

		let total = 0;
		lines.forEach((line) => {
			total += flt(line.rate) * flt(line.qty);
			const $line = $('<div class="ck-cart-line"></div>').attr("style", CK_STYLE.cart_line).appendTo(this.$cart_lines);
			$('<div class="ck-cart-line-name"></div>').attr("style", CK_STYLE.cart_line_name).text(line.article_name).appendTo($line);

			const $stepper = $('<div class="ck-stepper"></div>').attr("style", CK_STYLE.stepper).appendTo($line);
			$('<button class="btn btn-default btn-sm ck-step ck-step-minus">−</button>')
				.attr("style", CK_STYLE.step)
				.appendTo($stepper)
				.on("click", () => this._change_qty(line.article, -1));
			$('<span class="ck-step-qty"></span>').attr("style", CK_STYLE.step_qty).text(line.qty).appendTo($stepper);
			$('<button class="btn btn-default btn-sm ck-step ck-step-plus">+</button>')
				.attr("style", CK_STYLE.step)
				.appendTo($stepper)
				.on("click", () => this._change_qty(line.article, 1));
		});

		this._render_subtotal(total);
	}

	// Cart value subtotal (sum of qty x unit cost). Rendered only in Issue mode;
	// formatted via Frappe format_currency so Arabic-build digit grouping + SAR
	// symbol position are correct. The numeric value is bidi-isolated in a <bdi>.
	_render_subtotal(total) {
		if (!this.$subtotal) return;
		if (this.mode === "return") {
			this.$subtotal.empty().hide();
			return;
		}
		this.$subtotal.show().empty();
		$('<span class="ck-subtotal-label text-muted"></span>')
			.text(__("Estimated value"))
			.appendTo(this.$subtotal);
		$('<span class="ck-subtotal-value"></span>')
			.attr("style", CK_STYLE.subtotal_value)
			.append($("<bdi></bdi>").text(format_currency(flt(total), "SAR")))
			.appendTo(this.$subtotal);
	}

	// [#retcart]
	_render_return_cart() {
		this.$cart_lines.empty();
		this._render_subtotal(0);
		const lines = Object.values(this.return_cart);

		if (!lines.length) {
			$('<div class="ck-cart-empty text-muted"></div>')
				.attr("style", CK_STYLE.cart_empty)
				.text(__("Return cart is empty."))
				.appendTo(this.$cart_lines);
			this.$action_btn.prop("disabled", true);
			return;
		}

		this.$action_btn.prop("disabled", false);

		lines.forEach((line) => {
			const $line = $('<div class="ck-cart-line"></div>').attr("style", CK_STYLE.cart_line).appendTo(this.$cart_lines);
			const $info = $('<div class="ck-cart-line-info"></div>').attr("style", CK_STYLE.cart_line_info).appendTo($line);
			$('<div class="ck-cart-line-name"></div>').attr("style", CK_STYLE.cart_line_name_info).text(line.article_name).appendTo($info);
			$('<div class="ck-cart-line-sub text-muted"></div>')
				.attr("style", CK_STYLE.cart_line_sub)
				.text(line.custody_issue)
				.appendTo($info);

			const $stepper = $('<div class="ck-stepper"></div>').attr("style", CK_STYLE.stepper).appendTo($line);
			$('<button class="btn btn-default btn-sm ck-step ck-step-minus">−</button>')
				.attr("style", CK_STYLE.step)
				.appendTo($stepper)
				.on("click", () => this._change_return_qty(line.key, -1));
			$('<span class="ck-step-qty"></span>').attr("style", CK_STYLE.step_qty).text(line.qty).appendTo($stepper);
			const $plus = $(
				'<button class="btn btn-default btn-sm ck-step ck-step-plus">+</button>'
			)
				.attr("style", CK_STYLE.step)
				.appendTo($stepper)
				.on("click", () => this._change_return_qty(line.key, 1));
			// Cap at the held quantity.
			$plus.prop("disabled", !!line.max && line.qty >= line.max);
		});
	}

	_commit() {
		if (this.mode === "return") {
			this._return();
			return;
		}
		this._issue();
	}

	_issue() {
		const lines = Object.values(this.cart);
		if (!this.party) {
			frappe.show_alert({
				message: __("Select a worker before issuing."),
				indicator: "orange",
			});
			return;
		}
		if (!this.building) {
			frappe.show_alert({
				message: __("Select a building before issuing."),
				indicator: "orange",
			});
			return;
		}
		if (!lines.length) {
			frappe.show_alert({ message: __("Cart is empty."), indicator: "orange" });
			return;
		}

		const items = lines.map((l) => ({ article: l.article, qty: l.qty }));
		this._capture_signature((signature) => this._submit_issue(items, signature));
	}

	// Capture the recipient's signature at handover; signing is optional so the
	// kiosk still works when no pad input is taken (Skip submits without one).
	_capture_signature(on_done) {
		const dialog = new frappe.ui.Dialog({
			title: __("Recipient Signature"),
			fields: [
				{
					fieldname: "signature",
					fieldtype: "Signature",
					label: __("Sign to acknowledge receipt"),
				},
			],
			primary_action_label: __("Issue"),
			primary_action: () => {
				const signature = dialog.get_value("signature");
				dialog.hide();
				on_done(signature);
			},
			secondary_action_label: __("Skip"),
			secondary_action: () => {
				dialog.hide();
				on_done(null);
			},
		});
		dialog.show();
	}

	_submit_issue(items, signature) {
		this.$action_btn.prop("disabled", true);
		frappe.call({
			method: "apex.habitat.api.custody_kiosk.issue_cart",
			args: {
				party_type: this.party_type,
				party: this.party,
				building: this.building,
				items_json: JSON.stringify(items),
				signature: signature || null,
			},
			freeze: true,
			freeze_message: __("Issuing…"),
			callback: (r) => {
				if (r.exc || !r.message) {
					// [#c7lpcm]
					frappe.show_alert({
						message: __("Could not issue the cart. Please review and try again."),
						indicator: "red",
					});
					this._render_cart();
					return;
				}
				frappe.show_alert({
					message: __("Issued to {0}: {1}", [this.party, r.message.custody_issue]),
					indicator: "green",
				});
				this.cart = {};
				this._render_cart();
				this.refresh();
			},
			error: () => {
				frappe.show_alert({
					message: __("Could not issue the cart. Please review and try again."),
					indicator: "red",
				});
				this._render_cart();
			},
		});
	}

	// [#retcommit]
	_return() {
		const lines = Object.values(this.return_cart);
		if (!this.party) {
			frappe.show_alert({
				message: __("Select a worker before returning."),
				indicator: "orange",
			});
			return;
		}
		if (!lines.length) {
			frappe.show_alert({ message: __("Return cart is empty."), indicator: "orange" });
			return;
		}

		const items = lines.map((l) => ({
			custody_issue: l.custody_issue,
			article: l.article,
			qty: l.qty,
		}));

		this.$action_btn.prop("disabled", true);
		frappe.call({
			method: "apex.habitat.api.custody_kiosk.return_cart",
			args: {
				party_type: this.party_type,
				party: this.party,
				items_json: JSON.stringify(items),
			},
			freeze: true,
			freeze_message: __("Returning…"),
			callback: (r) => {
				if (r.exc || !r.message) {
					frappe.show_alert({
						message: __("Could not return the cart. Please review and try again."),
						indicator: "red",
					});
					this._render_cart();
					return;
				}
				const returns = r.message.custody_returns || [];
				frappe.show_alert({
					message: __("Returned from {0}: {1}", [this.party, returns.join(", ")]),
					indicator: "green",
				});
				this.return_cart = {};
				this._render_cart();
				this.refresh();
			},
			error: () => {
				frappe.show_alert({
					message: __("Could not return the cart. Please review and try again."),
					indicator: "red",
				});
				this._render_cart();
			},
		});
	}
}
