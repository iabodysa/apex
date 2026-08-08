// Copyright (c) 2026, afmcoltd
import { computed } from "vue";

/* One reader for the co-branding the Jinja shell publishes on `window`.
 *
 * Apex is the master identity and a tenant logo is a GUEST beside it, never a replacement —
 * so this returns the tenant logo separately instead of a single "the logo" value that a
 * caller could substitute. `portal_show_brand === false` hides the tenant guest; it does not
 * hide Apex.
 *
 * The logo is whatever the operator configured, so its accessible name is the configured
 * brand and never a client name written into the source. */
export function usePortalBrand() {
  const tenantLogo = computed(() => {
    const value = typeof window === "undefined" ? "" : window.portal_logo;
    return typeof value === "string" ? value.trim() : "";
  });

  const showTenant = computed(() => {
    if (typeof window === "undefined") return false;
    return window.portal_show_brand !== false && !!tenantLogo.value;
  });

  return { tenantLogo, showTenant };
}
