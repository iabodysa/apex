// Copyright (c) 2026, afmcoltd
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
} from "./fleetHelpers.js";

export function useFleetFormat(t) {
  const sb = (v) => {
    const k = statusKey(v.vehicle_status);
    return { ...SB[k], label: t("status." + k) };
  };
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

  function fuelView(v) {
    const planned = trim(v.planned_fuel_grade);
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
    statusKey, icon, initials, trim, today,
    calcTotalDaysNum, calcActiveDaysNum, historyItems,
    sb, sl, calcDur, fuelView, expiryFlag,
  };
}
