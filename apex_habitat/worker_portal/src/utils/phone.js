// Copyright (c) 2026, AFMCO and contributors
// [#1b17ho]
const DEFAULT_CC = "966"; // Saudi Arabia

export function normalizeMsisdn(phone, defaultCc = DEFAULT_CC) {
  let s = (phone || "").trim();
  if (!s) return "";
  const hadPlus = s.startsWith("+");
  // [#9u0ry2]
  let digits = s.replace(/[^\d]/g, "");
  if (!hadPlus && digits.startsWith("00")) {
    digits = digits.slice(2);
    return digits;
  }
  if (hadPlus) {
    // [#l4h9fo]
    return digits;
  }
  if (digits.startsWith(defaultCc)) {
    // [#m8lvz0]
    return digits;
  }
  if (digits.startsWith("0")) {
    // [#p2tu2m]
    return defaultCc + digits.slice(1);
  }
  // [#bnb1uo]
  return defaultCc + digits;
}

export function waLink(phone) {
  return "https://wa.me/" + normalizeMsisdn(phone);
}
