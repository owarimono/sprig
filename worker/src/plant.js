// Plant state logic and rendering. Pure functions only: no I/O, no env access,
// so the day-rollover / health / death rules stay testable (see test/plant.test.js).

export const STAGES = [
  "seed", "sprout", "sapling", "young", "mature",
  "tree", "blossom", "cherry", "ancient", "LEGENDARY",
];

export const PLANT_ART = [
  "      ·\n      ═╧═",
  "      │\n      │\n      ═╧═",
  "     ╱│╲\n      │\n     ═╧═",
  "    ╱╲╱╲\n     ╲│╱\n      │\n     ═╧═",
  "    ╱╲╱╲\n   ╱╱╲╱╱╲╲\n     ╲│╱\n     ═╧═",
  "   ╱╲╱╲╱╲\n  ╱╱╲╱╱╲╱╱╲╲\n    ╲╱╲│╱╲╱\n      │\n     ═╧═",
  " ·.·✧·.·\n  ╱╲╱╲╱╲╱╲\n ╱╱╲╱╱╲╱╱╲╱╱╲╲\n   ╲╱╲│╱╲╱\n     ═╧═",
  " ❀·.·✿·.·❀\n  ╱╲╱╲╱╲╱╲\n ╱╱╲╱╱╲╱╱╲╱╱╲╲\n╱╱╱╲╱╱╱╲╱╱╱╲╱╱╲╲╲\n   ╲╱╲│╱╲╱\n     ═╧═",
  " ✧·.·✦·.·✧·.·✦\n  ╱╲╱╲╱╲╱╲╱╲\n ╱╱╲╱╱╲╱╱╲╱╱╲╱╱╲╲\n╱╱╱╲╱╱╱╲╱╱╱╲╱╱╲╲╲\n  ╲╱╲│╱╲╱│╱╲╱\n   ═╧═══╧═",
  " ╔═══ LEGENDARY ═══╗\n ✦✧·.·✦✧·.·✦✧·.·✦\n  ╱╲╱╲╱╲╱╲╱╲╱╲\n ╱╱╲╱╱╲╱╱╲╱╱╲╱╱╲╱╱╲╲\n╱╱╱╲╱╱╱╲╱╱╱╲╱╱╲╲╲\n  ╲╱╲│╱╲╱│╱╲╱\n   ═╧═══╧═",
];

export const DEFAULT_LIMIT_MIN = 30;
export const LIMIT_MIN = 5;
export const LIMIT_MAX = 720;

const WARN_AT = 25;        // percent, one warning per day
const LEVEL_UP_EVERY = 3;  // good days per stage

const DAY_MS = 86400 * 1000;

// Whole days between two YYYY-MM-DD strings. Dates sort as UTC, no timezone math.
export function daysBetween(from, to) {
  const gap = (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS;
  return Number.isFinite(gap) ? Math.round(gap) : NaN;
}

export function bar(pct, w = 16) {
  const f = Math.max(0, Math.min(w, Math.round((pct / 100) * w)));
  return "█".repeat(f) + "░".repeat(w - f);
}

export function getStage(level) {
  return STAGES[Math.min(level, STAGES.length - 1)];
}

export function getArt(level) {
  return PLANT_ART[Math.min(level, PLANT_ART.length - 1)];
}

export function calcHealth(activeMin, limitMin = DEFAULT_LIMIT_MIN) {
  return Math.max(0, Math.round(100 - (activeMin * 100) / limitMin));
}

// Day boundary in the operator's timezone, not UTC: in UTC+03:30 a UTC day
// would roll over at 03:30 local. Intl is native to Workers, no dependency.
export function todayStr(tz = "UTC") {
  return new Date().toLocaleDateString("en-CA", { timeZone: tz });
}

export function newState(chatId, limitMin = DEFAULT_LIMIT_MIN, today = todayStr()) {
  return {
    chat_id: chatId,
    health: 100,
    level: 0,
    active_minutes_today: 0,
    limit_min: limitMin,
    last_date: today,
    last_status: "idle",
    consecutive_good_days: 0,
    total_plants_grown: 0,
    plant_alive: true,
    warned: false,
    paused: false,
  };
}

// Fill in fields missing from records written by earlier versions.
export function normalize(state, today = todayStr()) {
  const s = { ...newState(state.chat_id, DEFAULT_LIMIT_MIN, today), ...state };
  if (!Number.isFinite(s.limit_min) || s.limit_min <= 0) s.limit_min = DEFAULT_LIMIT_MIN;
  return s;
}

// The single owner of the daily reset. Returns the next state plus events for
// the caller to turn into messages. Never mutates the input.
export function applyPing(state, ping, today = todayStr()) {
  const s = { ...state };
  const events = [];

  if (s.paused) {
    s.last_status = "paused";
    return { state: s, events };
  }

  if (s.last_date !== today) {
    // Settle only the day immediately before today. After a pause or a gap of
    // untracked days there is nothing honest to credit: one stale settle used to
    // hand out a good day for a whole month of pause.
    const ended = daysBetween(s.last_date, today) === 1;
    if (ended && s.plant_alive && s.health >= 50) {
      s.consecutive_good_days += 1;
      s.total_plants_grown += 1;
      if (s.consecutive_good_days % LEVEL_UP_EVERY === 0 && s.level < STAGES.length - 1) {
        s.level += 1;
        events.push({ type: "grew", level: s.level });
      }
    } else if (ended) {
      s.consecutive_good_days = 0;
    }
    s.active_minutes_today = 0;
    s.health = 100;
    s.plant_alive = true;
    s.warned = false;
    s.last_date = today;
  }

  if (ping.status === "idle") {
    s.health = Math.min(100, s.health + 1);
  } else if (ping.status === "active") {
    s.active_minutes_today += 1;
    s.health = calcHealth(s.active_minutes_today, s.limit_min);
    if (!s.warned && s.health <= WARN_AT) {
      s.warned = true;
      events.push({ type: "warn", health: s.health });
    }
    if (s.health <= 0 && s.plant_alive) {
      s.plant_alive = false;
      events.push({ type: "died" });
    }
  } // any other status is ignored: no counting, no healing

  s.last_status = ping.status;
  return { state: s, events };
}

export function formatStatus(s) {
  const mood = s.paused
    ? "(--_) Tracking paused. /resume to continue."
    : s.plant_alive
      ? (s.health >= 50 ? "(n_n) Your plant is doing well!" : "(o_o) Your plant is struggling...")
      : "(;.;) Your plant died today...";

  return [
    "~ Plant Status ~",
    "",
    getArt(s.level),
    "",
    `Health:  [${bar(s.health)}] ${s.health}%`,
    `Stage:   Lv.${s.level} (${getStage(s.level)})`,
    `Today:   ${s.active_minutes_today} min active / ${s.limit_min} min limit`,
    "",
    mood,
    "",
    `Last ping: ${s.last_status || "none"}`,
    `Streak:   ${s.consecutive_good_days} days`,
    `Grown:    ${s.total_plants_grown} plants`,
  ].join("\n");
}

export function formatReport(s) {
  const survived = s.plant_alive && s.health >= 50;
  const result = s.paused ? "PAUSED (-_-)" : survived ? "SURVIVED (n_n)" : "DIED (;.;)";
  const note = s.paused
    ? "Tracking paused. /resume when you are back."
    : survived ? "Great job! Your plant lives on!" : "Tomorrow is a new day. Try again!";

  return [
    "~ Daily Report ~",
    "",
    getArt(s.level),
    "",
    `Health:  ${s.health}%`,
    `Used:    ${s.active_minutes_today} min / ${s.limit_min} min limit`,
    `Result:  ${result}`,
    `Streak:  ${s.consecutive_good_days} days`,
    `Total:   ${s.total_plants_grown} plants grown`,
    "",
    note,
  ].join("\n");
}
