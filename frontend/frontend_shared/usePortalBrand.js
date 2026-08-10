// Copyright (c) 2026, afmcoltd
import { computed } from "vue";

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
