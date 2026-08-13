const PARTY_TYPES = new Set(["Employee", "Temporary Worker"]);

export function arrivalRegistrationParams(form = {}, manifestRow = null, building = "") {
  return Object.freeze({
    ...form,
    building,
    ...(manifestRow ? {
      batch_row: manifestRow.row,
      labour_supplier: manifestRow.labour_supplier,
      project: manifestRow.project,
    } : {}),
  });
}

export function housingCandidateFromQuery(query = {}) {
  query = query && typeof query === "object" ? query : {};
  const partyType = typeof query.party_type === "string" ? query.party_type : "";
  const party = typeof query.party === "string" ? query.party : "";
  if (!PARTY_TYPES.has(partyType) || !party) return null;
  return Object.freeze({
    party_type: partyType,
    party,
    label: typeof query.label === "string" && query.label ? query.label : party,
    project: typeof query.project === "string" ? query.project : "",
  });
}

export function bedAssignmentTarget(bed, candidate) {
  const resolved = housingCandidateFromQuery(candidate);
  if (!resolved) return { path: `/beds/${bed}` };
  return {
    path: `/beds/${bed}`,
    query: {
      party_type: resolved.party_type,
      party: resolved.party,
      label: resolved.label,
      project: resolved.project,
    },
  };
}

export function normalizeWorkerLinkResult(result = []) {
  const row = Array.isArray(result) ? result[0] : result;
  if (!row?.link) return null;
  return Object.freeze({
    employee: row.employee,
    link: row.link,
    qr: row.qr || null,
    phone: row.phone || null,
  });
}

export function summarizeArrivalSession(workers = []) {
  const rows = Array.isArray(workers) ? workers : [];
  const registered = rows.filter((row) => row.arrived).length;
  const housed = rows.filter((row) => row.housed).length;
  const next = rows.find((row) => row.arrived && !row.housed)
    || rows.find((row) => !row.arrived)
    || null;
  return Object.freeze({
    total: rows.length,
    registered,
    housed,
    progress: rows.length ? Math.round((housed / rows.length) * 100) : 0,
    next,
    nextAction: next ? (next.arrived ? "assign-bed" : "register") : null,
  });
}
