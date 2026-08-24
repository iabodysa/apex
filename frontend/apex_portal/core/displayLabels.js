import { __ } from "./i18n.js";

const serverStateLabels = Object.freeze({
  scheduled: () => __("The trip is scheduled"),
  en_route: () => __("The bus is on its way"),
  at_stop: () => __("The bus is at your stop"),
  departed: () => __("The bus has left your stop"),
  finished: () => __("The trip has ended"),
  assigned: () => __("Assigned"),
  available: () => __("Available"),
  workshop: () => __("Under Maintenance"),
  stopped: () => __("Stopped"),
});

const maintenanceIssues = Object.freeze([
  "Electrical",
  "Plumbing",
  "Furniture",
  "Air Conditioning",
  "Fire Safety",
  "Pest Control",
  "Structural",
  "Other",
]);

const requestCategories = Object.freeze([
  "Maintenance",
  "Safety",
  "Cleaning",
  "Pest Control",
  "Custody",
  "Facility Item",
  "Water",
  "Electrical",
  "AC",
  "Plumbing",
  "Reimbursement",
  "Complaint",
  "Suggestion",
  "Other",
]);

const frappeDateTime = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.\d+)?)?$/;
const frappeTime = /^(\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.\d+)?)?$/;
const frappeDate = /^(\d{4})-(\d{2})-(\d{2})$/;

const dateStyle = { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Riyadh" };
const timeStyle = { hour: "numeric", minute: "2-digit", timeZone: "Asia/Riyadh" };
const formatters = new Map();

function clockFormatters() {
  const language = globalThis.document?.documentElement?.lang || "ar";
  let pair = formatters.get(language);
  if (!pair) {
    const locale = `${language}-u-ca-gregory-nu-latn`;
    pair = {
      date: new Intl.DateTimeFormat(locale, dateStyle),
      time: new Intl.DateTimeFormat(locale, timeStyle),
    };
    formatters.set(language, pair);
  }
  return pair;
}

function riyadhDate(parts) {
  const [year, month, day, hour = "00", minute = "00", second = "00"] = parts;
  return new Date(`${year}-${month}-${day}T${hour.padStart(2, "0")}:${minute.padStart(2, "0")}:${second.padStart(2, "0")}+03:00`);
}

export function optionLabel(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const state = serverStateLabels[text];
  return state ? state() : __(text);
}

export {
  optionLabel as cadenceLabel,
  optionLabel as conditionLabel,
  optionLabel as maintenanceIssueLabel,
  optionLabel as requestCategoryLabel,
  optionLabel as vehicleCategoryLabel,
};

const fieldLabelReaders = Object.freeze({
  issue_type: optionLabel,
  request_category: optionLabel,
  status: statusLabel,
  priority: statusLabel,
});

export function fieldLabel(field, value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const reader = fieldLabelReaders[field];
  return reader ? reader(text) : text;
}

export function maintenanceIssueOptions() {
  return maintenanceIssues.map((value) => ({ value, label: optionLabel(value) }));
}

export function requestCategoryOptions() {
  return requestCategories.map((value) => ({ value, label: optionLabel(value) }));
}

export function statusLabel(value) {
  return optionLabel(value) || __("New");
}

export function statusOptions(values = []) {
  return values.map((value) => ({ value, label: statusLabel(value) }));
}

export function workerTransportStatusLabel(value) {
  return statusLabel(value);
}

export function humanLabel(record, valueField, labelField, fallback = "") {
  return String(record?.[labelField] || fallback || record?.[valueField] || "").trim();
}

export function humanOptions(rows = [], valueField, labelField) {
  const options = new Map();
  for (const row of rows) {
    const value = String(row?.[valueField] || "").trim();
    if (!value || options.has(value)) continue;
    options.set(value, { value, label: humanLabel(row, valueField, labelField, value) });
  }
  return [...options.values()];
}

const greenStatuses = new Set([
  "Validated", "Approved", "Completed", "Fulfilled", "Ready", "Good", "Excellent",
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
  return match ? __("Floor {0}", [match[1]]) : text;
}

export function dateTimeLabel(value) {
  if (!value) return "";
  const text = String(value).trim();
  const { date: dateFormatter, time: timeFormatter } = clockFormatters();
  let match = text.match(frappeDateTime);
  if (match) {
    const moment = riyadhDate(match.slice(1));
    return __("{0} at {1}", [dateFormatter.format(moment), timeFormatter.format(moment)]);
  }
  match = text.match(frappeTime);
  if (match) {
    return timeFormatter.format(riyadhDate(["2000", "01", "01", ...match.slice(1)]));
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

export function recordTitle(record, fields = [], fallback = "") {
  for (const field of fields) {
    const value = String(record?.[field] || "").trim();
    if (value) return fieldLabel(field, value);
  }
  for (const field of ["title", "label"]) {
    const value = String(record?.[field] || "").trim();
    if (value) return value;
  }
  return fallback || __("Record");
}

export function periodLabel(period) {
  if (!period || typeof period !== "object") return "";
  if (period.kind === "day") return __("Today");
  if (period.kind === "week") return __("This week");
  if (period.kind === "month") return __("Month {0} of {1}", [period.month, period.year]);
  if (period.kind === "quarter") return __("Quarter {0} of {1}", [period.quarter, period.year]);
  if (period.kind === "year") return __("Year {0}", [period.year]);
  return "";
}
