// Copyright (c) 2026, AFMCO and contributors
// [#s7slet]
function readToken() {
  if (typeof window !== "undefined" && window.masar_token) {
    return String(window.masar_token).trim();
  }
  try {
    const params = new URLSearchParams(window.location.search);
    return (params.get("w") || "").trim();
  } catch (e) {
    return "";
  }
}

export const TOKEN = readToken();
export const hasToken = !!TOKEN;
