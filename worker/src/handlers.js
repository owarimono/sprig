import {
  applyPing, newState, normalize, formatStatus, formatReport, getStage,
  todayStr, DEFAULT_LIMIT_MIN, LIMIT_MIN, LIMIT_MAX,
} from "./plant.js";
import { sendMsg } from "./telegram.js";

const HELP = `~ Sprig ~

Commands:
  /start         - Plant your first plant
  /status        - Health, stage and today's usage
  /limit <min>   - Daily laptop budget (${LIMIT_MIN}-${LIMIT_MAX}, currently ${DEFAULT_LIMIT_MIN})
  /pause         - Stop counting (travel, day off)
  /resume        - Resume counting
  /reset         - Replace the plant with a fresh seed
  /help          - Show this message

Run client/sprig.py on your laptop to start tracking.

Stay inside the budget and the plant grows. Stay away and it heals.
Go over the limit and it dies.`;

const EVENTS = {
  grew: (e) => `Your plant grew to Lv.${e.level}! (${getStage(e.level)}) (b^_^)b`,
  warn: (e) => `(o_o) Health down to ${e.health}%. Close the laptop soon.`,
  died: () => "(;.;) Your plant died!\nToo much screen time today.\nTry again tomorrow!",
};

const key = (chatId) => String(chatId);
const tz = (env) => env.TZ || "UTC";
const today = (env) => todayStr(tz(env));

async function load(env, chatId) {
  const raw = await env.PLANT_KV.get(key(chatId));
  return raw ? normalize(JSON.parse(raw), today(env)) : null;
}

const save = (env, chatId, state) => env.PLANT_KV.put(key(chatId), JSON.stringify(state));

export async function handleStart(chatId, env) {
  if (await load(env, chatId)) {
    await sendMsg(env, chatId, "You already have a plant. /status to check it, /reset to replant.");
    return;
  }
  await save(env, chatId, newState(chatId, DEFAULT_LIMIT_MIN, today(env)));
  await sendMsg(env, chatId,
    "~ Welcome to Sprig ~\n\n" +
    "Your plant has been planted! (o^o)/\n\n" +
    "Run client/sprig.py on your laptop.\n" +
    `Budget: ${DEFAULT_LIMIT_MIN} min/day. Check with /status.`);
}

export async function handleStatus(chatId, env) {
  const s = await load(env, chatId);
  await sendMsg(env, chatId, s ? formatStatus(s) : "No plant found. Use /start first.");
}

export async function handleHelp(chatId, env) {
  await sendMsg(env, chatId, HELP);
}

export async function handleLimit(chatId, env, arg) {
  const s = await load(env, chatId);
  if (!s) {
    await sendMsg(env, chatId, "No plant found. Use /start first.");
    return;
  }
  const min = Number.parseInt(arg, 10);
  if (!Number.isInteger(min) || min < LIMIT_MIN || min > LIMIT_MAX) {
    await sendMsg(env, chatId, `Usage: /limit <${LIMIT_MIN}-${LIMIT_MAX}>. Current: ${s.limit_min} min/day.`);
    return;
  }
  s.limit_min = min;
  s.health = Math.min(s.health, Math.max(0, Math.round(100 - (s.active_minutes_today * 100) / min)));
  await save(env, chatId, s);
  await sendMsg(env, chatId, `Daily budget set to ${min} min/day. /status to see the effect.`);
}

export async function handlePause(chatId, env) {
  const s = await load(env, chatId);
  if (!s) {
    await sendMsg(env, chatId, "No plant found. Use /start first.");
    return;
  }
  s.paused = true;
  await save(env, chatId, s);
  await sendMsg(env, chatId, "(--_) Tracking paused. Your plant is frozen. /resume when you are back.");
}

export async function handleResume(chatId, env) {
  const s = await load(env, chatId);
  if (!s) {
    await sendMsg(env, chatId, "No plant found. Use /start first.");
    return;
  }
  s.paused = false;
  await save(env, chatId, s);
  await sendMsg(env, chatId, "(o^o) Tracking resumed. Welcome back!");
}

export async function handleReset(chatId, env) {
  await save(env, chatId, newState(chatId, DEFAULT_LIMIT_MIN, today(env)));
  await sendMsg(env, chatId, "A fresh seed is in the ground. Streak and stage reset. (o^o)/");
}

export async function handlePing(data, env) {
  if (data.token !== env.AUTH_TOKEN) return new Response("Unauthorized", { status: 401 });
  if (!data.chat_id) return new Response("Missing chat_id", { status: 400 });

  const s = (await load(env, data.chat_id)) || newState(data.chat_id, DEFAULT_LIMIT_MIN, today(env));
  const { state, events } = applyPing(s, data, today(env));

  await save(env, data.chat_id, state);
  for (const e of events) await sendMsg(env, data.chat_id, EVENTS[e.type](e));
  return new Response("OK");
}

// Reports only. The day is settled by the next ping, which is the single owner
// of the reset -- mutating state here used to resurrect a plant that had died.
export async function handleDailyReport(env) {
  const keys = await env.PLANT_KV.list();
  for (const k of keys.keys) {
    const raw = await env.PLANT_KV.get(k.name);
    if (!raw) continue;
    const s = normalize(JSON.parse(raw), today(env));
    if (!s.chat_id) continue;
    await sendMsg(env, s.chat_id, formatReport(s));
  }
}
