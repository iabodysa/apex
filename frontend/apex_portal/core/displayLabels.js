const statusLabels = Object.freeze({
  New: "جديد",
  Pending: "قيد الانتظار",
  Approved: "معتمد",
  Rejected: "مرفوض",
  Planned: "مجدولة",
  Dispatched: "في الطريق",
  Scheduled: "مجدولة",
  Fulfilled: "مكتملة",
  Unassigned: "غير مسندة",
  assigned: "مسندة",
  available: "متاحة",
  workshop: "في الورشة",
  stopped: "متوقفة",
  Started: "بدأت",
  Completed: "مكتملة",
  Cancelled: "ملغاة",
});

const frappeDateTime = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.\d+)?)?$/;
const frappeTime = /^(\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.\d+)?)?$/;
const frappeDate = /^(\d{4})-(\d{2})-(\d{2})$/;
const dateFormatter = new Intl.DateTimeFormat("ar-SA-u-ca-gregory-nu-latn", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Asia/Riyadh",
});
const timeFormatter = new Intl.DateTimeFormat("ar-SA-u-ca-gregory-nu-latn", {
  hour: "numeric",
  minute: "2-digit",
  timeZone: "Asia/Riyadh",
});

function riyadhDate(parts) {
  const [year, month, day, hour = "00", minute = "00", second = "00"] = parts;
  return new Date(`${year}-${month}-${day}T${hour.padStart(2, "0")}:${minute.padStart(2, "0")}:${second.padStart(2, "0")}+03:00`);
}

const cadenceLabels = Object.freeze({
  Daily: "يومية",
  Weekly: "أسبوعية",
  Monthly: "شهرية",
  Quarterly: "ربع سنوية",
  Annual: "سنوية",
});

const vehicleCategoryLabels = Object.freeze({
  Coach: "حافلة",
  "Crew Van": "فان طاقم",
  Minibus: "حافلة صغيرة",
});

export function statusLabel(value) {
  return statusLabels[value] || value || "جديد";
}

export function dateTimeLabel(value) {
  if (!value) return "";
  const text = String(value).trim();
  let match = text.match(frappeDateTime);
  if (match) {
    const date = riyadhDate(match.slice(1));
    return `${dateFormatter.format(date)}، ${timeFormatter.format(date)}`;
  }
  match = text.match(frappeTime);
  if (match) {
    const date = riyadhDate(["2000", "01", "01", ...match.slice(1)]);
    return timeFormatter.format(date);
  }
  match = text.match(frappeDate);
  if (match) return dateFormatter.format(riyadhDate(match.slice(1)));
  return text;
}

export function cadenceLabel(value) {
  return cadenceLabels[value] || value || "";
}

export function vehicleCategoryLabel(value) {
  return vehicleCategoryLabels[value] || value || "";
}

export function periodLabel(period) {
  if (!period || typeof period !== "object") return "";
  if (period.kind === "day") return "اليوم";
  if (period.kind === "week") return "هذا الأسبوع";
  if (period.kind === "month") return `شهر ${period.month} من ${period.year}`;
  if (period.kind === "quarter") return `الربع ${period.quarter} من ${period.year}`;
  if (period.kind === "year") return `عام ${period.year}`;
  return "";
}
