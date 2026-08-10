// Copyright (c) 2026, afmcoltd
import {
  EXPIRY_FLAG_DAYS,
  SB,
  calcActiveDaysNum,
  calcTotalDaysNum,
  historyItems,
  icon,
  initials,
  statusKey,
  today,
  trim,
} from "./fleetHelpers.js";

const STATUS_THEME = {
  assigned: "green",
  available: "blue",
  workshop: "orange",
  stopped: "gray",
  stolen: "red",
};

export function useFleetFormat(t) {
  const sb = (v) => {
    const key = statusKey(v.vehicle_status);
    return { ...SB[key], theme: STATUS_THEME[key], label: t("status." + key) };
  };
  const sl = (s) => t("statusShort." + statusKey(s));
  const statusTheme = (s) => STATUS_THEME[statusKey(s)];

  function calcDur(from, to) {
    if (!from) return "";
    const start = new Date(from);
    const end = to ? new Date(to) : new Date();
    const days = Math.round((end - start) / 86400000);
    if (Number.isNaN(days) || days < 0) return "";
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
    const daily = Number(v.planned_daily_fuel) || 0;
    return {
      gradeLabel,
      daily,
      dailyDisplay: daily > 0 ? daily.toFixed(1) : t("common.none"),
    };
  }

  function expiryFlag(v) {
    const status = trim(v.compliance_status);
    const dateStr = trim(v.next_expiry_date);
    let days = null;
    if (dateStr) {
      const exp = new Date(dateStr);
      if (!Number.isNaN(exp.getTime())) {
        days = Math.round((exp - new Date(today())) / 86400000);
      }
    }
    const expired = status === "Expired" || (days !== null && days < 0);
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
    statusKey,
    icon,
    initials,
    trim,
    today,
    calcTotalDaysNum,
    calcActiveDaysNum,
    historyItems,
    sb,
    sl,
    statusTheme,
    calcDur,
    fuelView,
    expiryFlag,
  };
}
