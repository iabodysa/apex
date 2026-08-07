// Copyright (c) 2026, afmcoltd
function detectHasToken() {
  if (typeof window !== "undefined" && typeof window.masar_has_token === "boolean") {
    return window.masar_has_token;
  }
  try {
    return !!(new URLSearchParams(window.location.search).get("w") || "").trim();
  } catch (e) {
    return false;
  }
}

export const TOKEN = "";
export const hasToken = detectHasToken();
