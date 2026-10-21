import test from "node:test";
import assert from "node:assert/strict";

import { handleDailyReport, handleLimit, handlePing, handleResume } from "../src/handlers.js";
import { newState } from "../src/plant.js";
import { todayStr } from "../src/plant.js";

// The Worker's only I/O is KV and fetch. A tiny in-memory KV with real paging
// semantics (list returns a cursor until the last page) lets the handlers run
// unchanged.
function fakeKV(records = {}, pageSize = 2) {
  const store = new Map(Object.entries(records));
  let writes = 0;
  return {
    writes: () => writes,
    store,
    async get(key) { return store.has(key) ? store.get(key) : null; },
    async put(key, value) { writes += 1; store.set(key, value); },
    async list({ cursor } = {}) {
      const names = [...store.keys()];
      const start = cursor ? Number(cursor) : 0;
      const keys = names.slice(start, start + pageSize).map((name) => ({ name }));
      const complete = start + pageSize >= names.length;
      return { keys, list_complete: complete, cursor: complete ? undefined : String(start + pageSize) };
    },
  };
}

const sent = [];
globalThis.fetch = async (_url, init) => {
  sent.push(JSON.parse(init.body));
  return new Response("{}", { status: 200 });
};

const envFor = (kv) => ({ PLANT_KV: kv, AUTH_TOKEN: "token", BOT_TOKEN: "bot", TZ: "UTC" });
const record = (chatId, extra = {}) =>
  JSON.stringify({ ...newState(chatId, 30, todayStr("UTC")), ...extra });

test("a lowered limit that today's usage already passed kills the plant", async () => {
  const kv = fakeKV({ 1: record(1, { active_minutes_today: 20, health: 33 }) });
  await handleLimit(1, envFor(kv), "5");
  const saved = JSON.parse(kv.store.get("1"));
  assert.equal(saved.health, 0);
  assert.equal(saved.plant_alive, false);
});

test("/limit rejects junk instead of parsing a number out of it", async () => {
  const kv = fakeKV({ 1: record(1) });
  await handleLimit(1, envFor(kv), "30abc");
  assert.equal(JSON.parse(kv.store.get("1")).limit_min, 30);
});

test("the daily report walks every KV page, not just the first", async () => {
  sent.length = 0;
  const kv = fakeKV({ 1: record(1), 2: record(2), 3: record(3) }, 2); // 2 pages
  await handleDailyReport(envFor(kv));
  assert.equal(sent.length, 3);
});

test("a paused ping writes nothing to KV", async () => {
  const kv = fakeKV({ 1: record(1, { paused: true, last_status: "paused" }) });
  await handlePing({ token: "token", chat_id: 1, status: "active" }, envFor(kv));
  assert.equal(kv.writes(), 0);
});

test("resume drops the paused days instead of settling one as good", async () => {
  const kv = fakeKV({ 1: record(1, { paused: true, last_date: "2026-01-01" }) });
  await handleResume(1, envFor(kv));
  const saved = JSON.parse(kv.store.get("1"));
  assert.equal(saved.last_date, todayStr("UTC"));
});
