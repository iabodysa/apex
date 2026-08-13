const INTERNAL_DETAIL = /(?:traceback|most recent call last|\bfile\s+["'][^"']+["']\s*,?\s*line\s+\d+|\/home\/frappe|\/apps\/|frappe\.|pymysql|mariadb|sqlalchemy|\bselect\b[\s\S]*\bfrom\b|\bat\s+\S+\s*\([^)]*:\d+:\d+\))/i;

function cleanText(value) {
  return String(value ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/^(?:[\w.]+\.)?(?:ValidationError|PermissionError|AuthenticationError|Error|Exception):\s*/i, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
}

function collectMessages(value, output, depth = 0) {
  if (value === null || value === undefined || depth > 4) return;
  if (Array.isArray(value)) {
    value.forEach((item) => collectMessages(item, output, depth + 1));
    return;
  }
  if (typeof value === "object") {
    if (value.message !== undefined) collectMessages(value.message, output, depth + 1);
    return;
  }
  const text = String(value).trim();
  if (!text) return;
  if (/^[\[{]/.test(text)) {
    try {
      collectMessages(JSON.parse(text), output, depth + 1);
      return;
    } catch {
      // A human message may legitimately start with punctuation.
    }
  }
  output.push(text);
}

function candidatesFrom(source) {
  const messages = [];
  if (source && typeof source === "object") {
    collectMessages(source._server_messages, messages);
    collectMessages(source.response?.data?._server_messages, messages);
    collectMessages(source.messages, messages);
    collectMessages(source.response?.data?.message, messages);
    collectMessages(source.message, messages);
  } else {
    collectMessages(source, messages);
  }
  return messages;
}

export function errorStatus(source) {
  const value = source?.status ?? source?.response?.status;
  if (value === null || value === undefined || value === "") return null;
  const status = Number(value);
  return Number.isInteger(status) && status >= 100 && status <= 599 ? status : null;
}

export function isRetryablePortalError(source) {
  return ![401, 403].includes(errorStatus(source));
}

export function safeErrorMessage(source, fallback = "تحقق من الاتصال ثم حاول مرة أخرى.", title = "") {
  for (const candidate of candidatesFrom(source)) {
    const clean = cleanText(candidate);
    if (!clean || clean === title || INTERNAL_DETAIL.test(clean)) continue;
    return clean;
  }
  return fallback;
}
