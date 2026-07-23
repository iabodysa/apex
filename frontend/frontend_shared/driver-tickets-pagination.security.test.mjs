// Copyright (c) 2026, AFMCO and contributors
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(import.meta.dirname, "../..");
const DRIVER = path.join(ROOT, "frontend/driver/src");
const TICKETS = path.join(DRIVER, "pages/Tickets.vue");
const PAGINATION = path.join(DRIVER, "ticketPagination.js");

test("ticket detail consumes bounded conversation pagination metadata", () => {
  const source = fs.readFileSync(TICKETS, "utf8");
  for (const marker of [
    "communication_offset",
    "communication_limit",
    "communication_has_more",
    "communication_next_offset",
    "loadMoreCommunications",
    "ticketGeneration",
    "isCurrentTicketRequest",
    "detailData",
  ]) {
    assert.match(source, new RegExp(marker));
  }
});

test("conversation pages accumulate with deterministic name deduplication", async () => {
  assert.equal(
    fs.existsSync(PAGINATION),
    true,
    "ticketPagination.js must provide the page accumulation boundary",
  );
  const { mergeCommunicationPages } = await import(PAGINATION);
  const first = [
    { name: "COMM-2", communication_date: "2026-07-19 10:00:00", creation: "2026-07-19 10:00:01" },
    { name: "COMM-1", communication_date: "2026-07-19 09:00:00", creation: "2026-07-19 09:00:01" },
  ];
  const next = [
    { name: "COMM-2", communication_date: "2026-07-19 10:00:00", creation: "2026-07-19 10:00:01", content: "updated" },
    { name: "COMM-3", communication_date: "2026-07-19 10:00:00", creation: "2026-07-19 10:00:02" },
  ];

  const merged = mergeCommunicationPages(first, next);

  assert.deepEqual(merged.map(({ name }) => name), ["COMM-1", "COMM-2", "COMM-3"]);
  assert.equal(merged.find(({ name }) => name === "COMM-2").content, "updated");
});

test("late ticket pages are rejected after navigation changes generation", async () => {
  const pagination = await import(PAGINATION);
  assert.equal(
    typeof pagination.isCurrentTicketRequest,
    "function",
    "ticketPagination.js must expose the stale-response guard",
  );

  let release;
  const latePage = new Promise((resolve) => { release = resolve; });
  const requested = { ticket: "ISSUE-A", generation: 1 };
  let active = requested;
  let rendered = [];
  const pending = latePage.then((page) => {
    if (pagination.isCurrentTicketRequest(requested, active)) rendered = page;
  });

  active = { ticket: "ISSUE-B", generation: 2 };
  release([{ name: "COMM-A" }]);
  await pending;

  assert.deepEqual(rendered, []);
  assert.equal(
    pagination.isCurrentTicketRequest(active, active),
    true,
    "the active ticket request must still be accepted",
  );
});

test("late reply completion is ignored after navigation changes generation", async () => {
  const source = fs.readFileSync(TICKETS, "utf8");
  const submitReply = source.slice(
    source.indexOf("function submitReply()"),
    source.indexOf("// Map ticket status"),
  );
  assert.match(submitReply, /const requested = activeTicketRequest\(\)/);
  assert.match(submitReply, /reply\.submit\([\s\S]*onSuccess:/);
  assert.match(
    submitReply,
    /isCurrentTicketRequest\(requested, activeTicketRequest\(\)\)/,
  );

  const { isCurrentTicketRequest } = await import(PAGINATION);
  let release;
  const lateReply = new Promise((resolve) => { release = resolve; });
  const requested = { ticket: "ISSUE-A", generation: 1 };
  let active = requested;
  let reloads = 0;
  const pending = lateReply.then(() => {
    if (isCurrentTicketRequest(requested, active)) reloads += 1;
  });

  active = { ticket: "ISSUE-B", generation: 2 };
  release();
  await pending;

  assert.equal(reloads, 0);
});
