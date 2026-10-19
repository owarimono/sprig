import {
  handleStart, handleStatus, handleHelp, handleLimit, handlePause,
  handleResume, handleReset, handlePing, handleDailyReport,
} from "./handlers.js";
import { todayStr } from "./plant.js";

const COMMANDS = {
  start: (chatId, env) => handleStart(chatId, env),
  status: (chatId, env) => handleStatus(chatId, env),
  help: (chatId, env) => handleHelp(chatId, env),
  limit: (chatId, env, arg) => handleLimit(chatId, env, arg),
  pause: (chatId, env) => handlePause(chatId, env),
  resume: (chatId, env) => handleResume(chatId, env),
  reset: (chatId, env) => handleReset(chatId, env),
};

async function onWebhook(request, env) {
  // Telegram signs every update when the webhook was registered with secret_token.
  if (env.WEBHOOK_SECRET &&
      request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
    return new Response("Forbidden", { status: 403 });
  }

  let update;
  try {
    update = await request.json();
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  const text = (update.message?.text || "").trim().replace(/^\/(\w+)@\S+/, "/$1");
  const [word, arg] = text.split(/\s+/);
  const handler = COMMANDS[word.slice(1).toLowerCase()];
  if (handler) await handler(update.message.chat.id, env, arg);

  return new Response("OK");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/webhook" && request.method === "POST") {
      return onWebhook(request, env);
    }

    if (url.pathname === "/ping" && request.method === "POST") {
      let data;
      try {
        data = await request.json();
      } catch {
        return new Response("Bad Request", { status: 400 });
      }
      return handlePing(data, env);
    }

    return new Response("Laptop Guardian");
  },

  async scheduled(event, env) {
    await handleDailyReport(env, todayStr(env.TZ || "UTC"));
  },
};
