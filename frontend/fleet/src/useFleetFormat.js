// Copyright (c) 2026, AFMCO and contributors
// Display formatters that need i18n (t). Bundles the pure helpers with the
// t-bound ones into ONE `fmt` object so App.vue and the presentational
// components have a single formatting source (call sites stay `sb(v)` etc.).
import {
  SB,
  EXPIRY_FLAG_DAYS,
  statusKey,
  icon,
  initials,
  trim,
  today,
  calcTotalDaysNum,
  calcActiveDaysNum,
  historyItems,
  serverMsg,
} from "./fleetHelpers.js";

export function useFleetFormat(t) {
  // Status badge (static class/icon from SB + reactively-translated label).
  const sb = (v) => {
    const k = statusKey(v.vehicle_status);
    return { ...SB[k], label: t("status." + k) };
  };
  // Table short label for a status.
  const sl = (s) => t("statusShort." + statusKey(s));

  function calcDur(from, to) {
    if (!from) return "";
    const d1 = new Date(from);
    const d2 = to ? new Date(to) : new Date();
    const days = Math.round((d2 - d1) / 86400000);
    if (isNaN(days) || days < 0) return "";
    if (days > 365) return t("duration.months", { n: Math.round(days / 30) });
    return t("duration.days", { n: days });
  }

  // Fuel display values. Prefers the vehicle's real planned-fuel plan
  // (planned_fuel_grade + planned_daily_fuel off Salis Vehicle); falls back
  // to the category fuel type only to pick a sensible grade label.
  function fuelView(v) {
    const planned = trim(v.planned_fuel_grade); // "Petrol 91" | "Petrol 95" | "Diesel" | ""
    const catType = trim(v.fuel).toUpperCase();
    const isDiesel = planned ? /diesel/i.test(planned) : catType === "DESIL" || catType === "DIESEL";
    const is95 = /95/.test(planned);
    const gradeLabel = isDiesel
      ? t("fuelGrade.diesel")
      : is95
        ? t("fuelGrade.petrol95")
        : t("fuelGrade.petrol91");
    const sarPerL = isDiesel ? 0.69 : is95 ? 2.33 : 2.18;
    const dailySAR = Number(v.planned_daily_fuel) || 0;
    return {
      gradeLabel,
      sarPerL,
      dailySAR,
      sarDisplay: dailySAR > 0 ? dailySAR.toFixed(1) : "—",
      monDisplay: dailySAR > 0 ? (dailySAR * 30).toFixed(0) : "—",
    };
  }

  // Compliance flag for the card. Flags a vehicle whose next compliance document
  // expires within 7 days (or is already expired); a Compliant vehicle with a far
  // expiry is never flagged. The read-only compliance_status is honoured as a
  // backstop so a flag still shows when the server marked it but the date is missing.
  function expiryFlag(v) {
    const status = trim(v.compliance_status);
    const dateStr = trim(v.next_expiry_date);
    let days = null;
    if (dateStr) {
      const exp = new Date(dateStr);
      if (!isNaN(exp)) {
        const start = new Date(today());
        days = Math.round((exp - start) / 86400000);
      }
    }
    const expired = status === "Expired" || days !== null && days < 0;
    const nearExpiry = days !== null && days >= 0 && days <= EXPIRY_FLAG_DAYS;
    // Never flag a Compliant vehicle unless the date itself is genuinely near.
    const flaggedByStatus = status === "Expired" || status === "Expiring Soon";
    const show = expired || nearExpiry || (flaggedByStatus && days === null);
    return {
      show,
      expired,
      days,
      status,
      date: dateStr,
      label: expired
        ? t("card.expired")
        : days !== null
          ? t("card.expiresInDays", { n: days })
          : t("card.expiringSoon"),
    };
  }

  return {
    // pure passthrough (single formatting source for the template)
    statusKey, icon, initials, trim, today,
    calcTotalDaysNum, calcActiveDaysNum, historyItems, serverMsg,
    // t-bound
    sb, sl, calcDur, fuelView, expiryFlag,
  };
}
