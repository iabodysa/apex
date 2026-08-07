// Copyright (c) 2026, afmcoltd
const DEFAULT_CC = "966";

export function normalizeMsisdn(phone, defaultCc = DEFAULT_CC) {
  let s = (phone || "").trim();
  if (!s) return "";
  const hadPlus = s.startsWith("+");
  let digits = s.replace(/[^\d]/g, "");
  if (!hadPlus && digits.startsWith("00")) {
    digits = digits.slice(2);
    return digits;
  }
  if (hadPlus) {
    return digits;
  }
  if (digits.startsWith(defaultCc)) {
    return digits;
  }
  if (digits.startsWith("0")) {
    return defaultCc + digits.slice(1);
  }
  return defaultCc + digits;
}

export function waLink(phone) {
  return "https://wa.me/" + normalizeMsisdn(phone);
}
