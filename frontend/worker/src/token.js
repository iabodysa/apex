// Copyright (c) 2026, afmcoltd

export const hasToken = (() => {
  if (typeof window !== "undefined" && typeof window.masar_has_token === "boolean") {
    return window.masar_has_token;
  }
  try {
    return !!(new URLSearchParams(window.location.search).get("w") || "").trim();
  } catch (e) {
    return false;
  }
})();
