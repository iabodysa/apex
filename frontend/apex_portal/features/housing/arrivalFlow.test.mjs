import { describe, expect, it } from "vitest";

import {
  arrivalRegistrationParams,
  bedAssignmentTarget,
  housingCandidateFromQuery,
} from "./arrivalFlow.js";

describe("housing arrival flow", () => {
  it("keeps the manifest context when registering a temporary worker", () => {
    expect(arrivalRegistrationParams(
      { worker_name: "عامل", passport_number: "P-1", nationality: "Indian" },
      { row: "ROW-1", labour_supplier: "SUP-1", project: "PROJ-1" },
      "BLD-1",
    )).toEqual({
      worker_name: "عامل",
      passport_number: "P-1",
      nationality: "Indian",
      building: "BLD-1",
      batch_row: "ROW-1",
      labour_supplier: "SUP-1",
      project: "PROJ-1",
    });
  });

  it("carries one server-resolved party from arrivals to the selected bed", () => {
    const candidate = {
      party_type: "Temporary Worker",
      party: "TW-1",
      label: "عامل مؤقت",
      project: "PROJ-1",
    };
    const target = bedAssignmentTarget("BED-1", candidate);

    expect(target).toEqual({
      path: "/beds/BED-1",
      query: {
        party_type: "Temporary Worker",
        party: "TW-1",
        label: "عامل مؤقت",
        project: "PROJ-1",
      },
    });
    expect(housingCandidateFromQuery(target.query)).toEqual(candidate);
  });

  it("rejects an incomplete client query instead of inventing a resident", () => {
    expect(housingCandidateFromQuery({ party_type: "Employee" })).toBeNull();
  });
});
