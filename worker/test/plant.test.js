import test from "node:test";
import assert from "node:assert/strict";

import {
  applyPing, newState, normalize, calcHealth, todayStr, daysBetween, LIMIT_MIN,
} from "../src/plant.js";

const D1 = "2026-01-01";
const D2 = "2026-01-02";

test("health drains over the daily limit and kills the plant", () => {
  let s = newState(1, 30, D1);
  let died = false;
  for (let i = 0; i < 30; i++) {
    const r = applyPing(s, { status: "active" }, D1);
    s = r.state;
    died ||= r.events.some((e) => e.type === "died");
  }
  assert.equal(s.health, 0);
  assert.equal(s.plant_alive, false);
  assert.ok(died);
});

test("a dead plant earns no good day (the daily report must not forgive it)", () => {
  const dead = { ...newState(1, 30, D1), health: 0, plant_alive: false };
  const { state, events } = applyPing(dead, { status: "idle" }, D2);
  assert.equal(state.consecutive_good_days, 0);
  assert.equal(state.total_plants_grown, 0);
  assert.deepEqual(events, []);
  assert.equal(state.plant_alive, true); // a new day starts a new plant
  assert.equal(state.health, 100);
});

test("three good days level the plant up", () => {
  let s = newState(1, 30, D1);
  let grew = false;
  for (const day of ["2026-01-02", "2026-01-03", "2026-01-04"]) {
    const r = applyPing(s, { status: "idle" }, day);
    s = r.state;
    grew ||= r.events.some((e) => e.type === "grew");
  }
  assert.equal(s.consecutive_good_days, 3);
  assert.equal(s.level, 1);
  assert.ok(grew);
});

test("one warning per day, at 25% health", () => {
  let s = newState(1, 4, D1);
  const warns = [];
  for (let i = 0; i < 4; i++) {
    const r = applyPing(s, { status: "active" }, D1);
    s = r.state;
    warns.push(...r.events.filter((e) => e.type === "warn"));
  }
  assert.equal(calcHealth(3, 4), 25);
  assert.equal(warns.length, 1);
});

test("pause freezes the day, including the spent budget", () => {
  const s = { ...newState(1, 30, D1), paused: true, active_minutes_today: 12, health: 60 };
  const { state } = applyPing(s, { status: "active" }, D2);
  assert.equal(state.active_minutes_today, 12);
  assert.equal(state.health, 60);
  assert.equal(state.last_date, D1); // rollover deferred until resume
});

test("an unknown status neither counts nor heals", () => {
  const s = { ...newState(1, 30, D1), health: 50 };
  assert.equal(applyPing(s, { status: "weird" }, D1).state.health, 50);
});

test("the same day is never settled twice", () => {
  let s = newState(1, 30, D1);
  s = applyPing(s, { status: "idle" }, D2).state;
  s = applyPing(s, { status: "idle" }, D2).state;
  assert.equal(s.consecutive_good_days, 1);
});

test("records from older versions are filled in, not dropped", () => {
  const s = normalize({ chat_id: 7, health: 80, level: 2, limit_min: 0 });
  assert.equal(s.limit_min, 30);
  assert.equal(s.level, 2);
  assert.equal(s.health, 80);
  assert.equal(s.consecutive_good_days, 0);
});

test("a gap of untracked days credits no good day", () => {
  const s = { ...newState(1, 30, D1), health: 100 };
  const { state } = applyPing(s, { status: "idle" }, "2026-01-06");
  assert.equal(state.consecutive_good_days, 0);
  assert.equal(state.total_plants_grown, 0);
  assert.equal(daysBetween(D1, "2026-01-06"), 5);
  assert.equal(daysBetween(D1, D2), 1);
});

test("todayStr renders a YYYY-MM-DD day in the requested timezone", () => {
  assert.match(todayStr("Asia/Tehran"), /^\d{4}-\d{2}-\d{2}$/);
  assert.match(todayStr("UTC"), /^\d{4}-\d{2}-\d{2}$/);
});

test("limit bounds are sane", () => {
  assert.ok(LIMIT_MIN > 0);
});
