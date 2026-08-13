export function filtersFromQuery(query = {}, { base = {}, dateField = "" } = {}) {
  const filters = { ...base };
  if (query.status) filters.status = query.status;
  if (query.project) filters.project = query.project;
  if (query.date && dateField) {
    filters[dateField] = ["between", [`${query.date} 00:00:00`, `${query.date} 23:59:59`]];
  }
  return filters;
}

export function queryFromFilters(filters = {}) {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => typeof value === "string" && value),
  );
}

export function resultCountLabel(count, hasMore) {
  const suffix = hasMore ? " مع نتائج إضافية" : "";
  return `${count} ${count === 1 ? "نتيجة" : "نتائج"}${suffix}`;
}
