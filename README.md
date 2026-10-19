# Laptop Guardian

A Telegram bot that grows a plant while you stay off your laptop, and kills it
when you overuse it. Stay inside your daily budget and the plant levels up.
Walk away and it heals. Go over the limit and it dies.

No accounts, no app to install: a stdlib-only Python client reports whether the
machine is in use, a Cloudflare Worker keeps the plant, Telegram is the UI.

## How it works

```
laptop                                    cloud
  guardian.py                             Worker  (/ping)
    probe idle seconds  ---------------->  applyPing()
    status = idle | active                 plant state in KV
                                           |
  Telegram  <---- daily report + events <--+  cron 23:55 local
```

The Worker is the only place that decides what a plant looks like: `src/plant.js`
holds every rule as a pure function, `src/handlers.js` only does I/O and messages.

## Layout

```
client/guardian.py        idle detector + reporter (standard library only)
worker/src/index.js       routes: /webhook, /ping, scheduled report
worker/src/handlers.js    Telegram commands, KV reads and writes
worker/src/plant.js       plant rules and message rendering (pure)
worker/src/telegram.js    sendMessage wrapper
worker/test/plant.test.js node --test, no dependencies
```

## Commands

| Command | Effect |
| --- | --- |
| `/start` | Plant your first plant. Does not overwrite an existing one. |
| `/status` | Health bar, stage, today's usage, streak. |
| `/limit <min>` | Daily laptop budget, 5-720 minutes. Default 30. |
| `/pause` | Freeze the plant while you travel or take a day off. |
| `/resume` | Resume counting. |
| `/reset` | Replace the plant with a fresh seed. Streak and stage reset. |
| `/help` | Command list. |

## Setup

1. Create the KV namespace and paste its id into `worker/wrangler.toml`:

   ```sh
   cd worker
   npx wrangler kv:namespace create PLANT_KV
   ```

2. Set the secrets (`AUTH_TOKEN` is any strong random string you invent):

   ```sh
   npx wrangler secret put BOT_TOKEN        # from @BotFather
   npx wrangler secret put AUTH_TOKEN
   npx wrangler secret put WEBHOOK_SECRET   # also passed to setWebhook below
   ```

3. Deploy and register the webhook:

   ```sh
   npx wrangler deploy
   curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
     -d "url=https://<worker>.workers.dev/webhook" \
     -d "secret_token=<WEBHOOK_SECRET>"
   ```

4. Send `/start` to your bot, then run the client:

   ```sh
   export WORKER_URL=https://<worker>.workers.dev
   export AUTH_TOKEN=...
   export CHAT_ID=...
   python3 client/guardian.py --dry-run   # which idle backend is available?
   python3 client/guardian.py             # start reporting
   ```

## Idle detection

Probed in order, first one that answers wins:

| Backend | Needs | Notes |
| --- | --- | --- |
| `logind` | systemd | Reads `IdleHint` / `IdleSinceHintMonotonic` over the system bus. Works on X11 and Wayland. |
| `xprintidle` | `xprintidle` | X11 and XWayland only. |
| `xssstate` | `xssstate` | X11 only. |
| `screensaver` | a desktop implementing `org.freedesktop.ScreenSaver` | `GetActive` is a boolean, so idle time is only "at least the threshold". |

If no backend answers, the client reports nothing instead of reporting "active":
a broken probe must not count every minute as usage and kill the plant.

## Client environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `WORKER_URL` | required | Worker base URL |
| `AUTH_TOKEN` | required | Shared secret, must match the Worker |
| `CHAT_ID` | required | Telegram chat to report to |
| `IDLE_THRESHOLD` | `300` | Seconds of inactivity that count as away |
| `PING_INTERVAL` | `60` | Seconds between pings. One ping while active equals one minute of usage. |

## Tests

```sh
cd worker && npm test
```

Covers the day rollover, limit and death rules, the pause freeze, warning
deduplication, backwards compatibility with old KV records and the timezone
helper.

## Notes

- Cron schedules are UTC. `TZ` in `wrangler.toml` sets the day boundary for
  rollover and reporting; keep the cron expression shifted to match it.
- One active ping equals one minute of usage. The client keeps a fixed cadence
  so the count stays honest.
- State is one KV record per chat, written on every ping. Concurrent pings for
  the same chat could lose an update; there is one client per plant, so this is
  left alone.
