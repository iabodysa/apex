import { describe, expect, it } from "vitest";

import {
  arrivalRegistrationParams,
  bedAssignmentTarget,
  housingCandidateFromQuery,
  summarizeArrivalSession,
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

  it("opens an ordinary bed when no arrival candidate was selected", () => {
    expect(bedAssignmentTarget("BED-1", null)).toEqual({ path: "/beds/BED-1" });
  });

  it("advances a reception session from registration to bed assignment", () => {
    const workers = [
      { row: "ROW-1", worker_name: "عامل أ", arrived: false, housed: false },
      { row: "ROW-2", worker_name: "عامل ب", arrived: true, housed: false, temporary_worker: "TW-2" },
      { row: "ROW-3", worker_name: "عامل ج", arrived: true, housed: true, temporary_worker: "TW-3" },
    ];

    expect(summarizeArrivalSession(workers)).toMatchObject({
      total: 3,
      registered: 2,
      housed: 1,
      progress: 33,
      next: workers[1],
      nextAction: "assign-bed",
    });
  });
});
