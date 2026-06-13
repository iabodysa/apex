/* Phone-number helpers for the Masar worker portal.
 *
 * wa.me requires a full international number in DIGITS ONLY (no "+", no spaces).
 * Saudi mobiles are usually stored locally as "05XXXXXXXX" or "5XXXXXXXX"; a bare
 * digit-strip would hand wa.me a national number and WhatsApp would fail to open
 * the chat. normalizeMsisdn() resolves a number to E.164 digits, defaulting to
 * the Saudi country code (966) when no country code is present. */
const DEFAULT_CC = "966"; // Saudi Arabia

export function normalizeMsisdn(phone, defaultCc = DEFAULT_CC) {
  let s = (phone || "").trim();
  if (!s) return "";
  const hadPlus = s.startsWith("+");
  // "00" international prefix → drop it (becomes a leading country code).
  let digits = s.replace(/[^\d]/g, "");
  if (!hadPlus && digits.startsWith("00")) {
    digits = digits.slice(2);
    return digits;
  }
  if (hadPlus) {
    // Already explicit international form (e.g. +966 5..., +20 ...): trust it.
    return digits;
  }
  if (digits.startsWith(defaultCc)) {
    // Already carries the default country code.
    return digits;
  }
  if (digits.startsWith("0")) {
    // National trunk-prefixed local number → swap the leading 0 for the CC.
    return defaultCc + digits.slice(1);
  }
  // Bare national subscriber number (e.g. 5XXXXXXXX) → prepend the CC.
  return defaultCc + digits;
}

export function waLink(phone) {
  return "https://wa.me/" + normalizeMsisdn(phone);
}
