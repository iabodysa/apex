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
  Ready: "جاهزة",
  "Needs Cleaning": "تحتاج تنظيف",
  "Needs Repair": "تحتاج إصلاح",
  "Out of Service": "خارج الخدمة",
  Available: "متاح",
  Occupied: "مشغول",
  Good: "جيدة",
  Excellent: "ممتازة",
  Average: "متوسطة",
  Poor: "ضعيفة",
  "Not Done": "لم تُنفذ",
  High: "عالية",
  Medium: "متوسطة",
  Low: "منخفضة",
  Active: "نشط",
  Inactive: "غير نشط",
  Exhausted: "مستنفد",
  Closed: "مغلق",
  Open: "مفتوح",
  Unknown: "غير معروف",
  Scrapped: "مستبعد",
  Stopped: "متوقف",
  "On Leave": "في إجازة",
  "Under Maintenance": "تحت الصيانة",
  Released: "خارج العهدة",
  "Not Tracked": "غير متابع",
  Compliant: "ملتزم",
  "Expiring Soon": "ينتهي قريباً",
  Expired: "منتهي",
  Valid: "ساري",
  Standard: "عادي",
  Additional: "إضافي",
  Draft: "مسودة",
  "In Progress": "قيد التنفيذ",
  Resolved: "محلول",
  Reopened: "أعيد فتحه",
  "Pending Approval": "بانتظار الاعتماد",
  "Pending Receipt": "بانتظار الاستلام",
  "Pending Exits": "بانتظار الخروج",
  "Under Review": "قيد المراجعة",
  Confirmed: "مؤكد",
  Issued: "مصروف",
  Returned: "مسترجع",
  "Partially Returned": "مسترجع جزئياً",
  Lost: "مفقود",
  Damaged: "تالف",
  "In Transit": "في الطريق",
  Received: "مستلم",
  Delivered: "تم التسليم",
  Failed: "فشل",
  Reverted: "أعيد",
  Done: "منجز",
  Triaged: "مصنف",
  Assigned: "مسند",
  "Waiting Evidence": "بانتظار الإثبات",
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

const inventoryConditionLabels = Object.freeze({
  New: "جديدة",
  Good: "جيدة",
  Fair: "مقبولة",
  "Needs Maintenance": "تحتاج صيانة",
  Damaged: "تالفة",
  Missing: "مفقودة",
});

export function statusLabel(value) {
  return statusLabels[value] || value || "جديد";
}

const greenStatuses = new Set([
  "Approved", "Completed", "Fulfilled", "Ready", "Good", "Excellent",
  "Active", "Closed", "Resolved", "Confirmed", "Received", "Delivered", "Done",
  "Available", "Valid", "Issued", "Returned", "assigned",
]);
const redStatuses = new Set([
  "Rejected", "Failed", "Cancelled", "Damaged", "Lost", "Expired", "Poor", "Not Done",
]);
const orangeStatuses = new Set([
  "Pending", "Open", "In Progress", "Pending Approval", "Pending Receipt",
  "Pending Exits", "Under Review", "Needs Cleaning", "Needs Repair", "Expiring Soon",
  "Under Maintenance", "In Transit", "Waiting Evidence", "Triaged", "Assigned",
]);

export function statusTheme(value) {
  if (greenStatuses.has(value)) return "green";
  if (redStatuses.has(value)) return "red";
  if (orangeStatuses.has(value)) return "orange";
  return "gray";
}

export function floorLabel(value) {
  const text = String(value || "");
  const match = text.match(/^Floor\s+(.+)$/i);
  return match ? `الطابق ${match[1]}` : text;
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

export function remainingSeconds(value, durationSeconds, now = Date.now()) {
  if (!value) return null;
  const text = String(value).trim();
  const match = text.match(frappeDateTime);
  const started = match
    ? riyadhDate(match.slice(1)).getTime()
    : Date.parse(text);
  if (!Number.isFinite(started)) return null;
  const duration = Math.max(Number(durationSeconds) || 0, 0) * 1000;
  return Math.max(Math.ceil((started + duration - now) / 1000), 0);
}

export function cadenceLabel(value) {
  return cadenceLabels[value] || value || "";
}

export function vehicleCategoryLabel(value) {
  return vehicleCategoryLabels[value] || value || "";
}

export function conditionLabel(value) {
  return inventoryConditionLabels[value] || value || "";
}

export function recordTitle(record, fields = [], fallback = "سجل") {
  for (const field of fields) {
    const value = String(record?.[field] || "").trim();
    if (value) return value;
  }
  for (const field of ["title", "label"]) {
    const value = String(record?.[field] || "").trim();
    if (value) return value;
  }
  return fallback;
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
