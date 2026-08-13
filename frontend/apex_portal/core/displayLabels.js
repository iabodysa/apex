const statusLabels = Object.freeze({
  New: "جديد",
  Pending: "قيد الانتظار",
  Approved: "معتمد",
  Rejected: "مرفوض",
  Started: "بدأت",
  Completed: "مكتملة",
  Cancelled: "ملغاة",
});

const cadenceLabels = Object.freeze({
  Daily: "يومية",
  Weekly: "أسبوعية",
  Monthly: "شهرية",
  Quarterly: "ربع سنوية",
  Annual: "سنوية",
});

export function statusLabel(value) {
  return statusLabels[value] || value || "جديد";
}

export function cadenceLabel(value) {
  return cadenceLabels[value] || value || "";
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
