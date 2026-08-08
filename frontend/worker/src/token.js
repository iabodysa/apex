// Copyright (c) 2026, afmcoltd

/* The secret itself never reaches this bundle. `apex/www/masar.py` charset-guards the
   `?w=` parameter, throttles it, writes the httpOnly SameSite=Lax cookie and redirects
   to the clean path; the shell is told only whether that cookie exists. Every call
   below therefore sends no credential at all — the server reads the cookie. */
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
