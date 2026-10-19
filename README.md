<div align="center">

```
 ✧·.·✦·.·✧·.·✦
  ╱╲╱╲╱╲╱╲╱╲
 ╱╱╲╱╱╲╱╱╲╱╱╲╱╱╲╲
╱╱╱╲╱╱╱╲╱╱╱╲╱╱╲╲╲
  ╲╱╲│╱╲╱│╱╲╱
   ═╧═══╧═
```

# Sprig

**Grow a plant by staying off your computer.**

Stay inside your daily screen-time budget and it levels up.
Walk away and it heals. Go over the limit and it dies.

![license](https://img.shields.io/badge/license-ISC-2ea44f)
![python](https://img.shields.io/badge/python-3.8%2B-3776ab)
![dependencies](https://img.shields.io/badge/dependencies-none-8a2be2)

</div>

---

## What it is

A plant that lives in your Telegram chat and measures how much you use your
computer. Not a timer you can ignore: it spends something.

- **The rule.** A daily budget of screen time, 30 minutes by default. Stay under it
  and the plant is healthy. Go over it and health drains to zero.
- **Getting away heals it.** Five idle minutes and a ping counts as away, which
  restores a little health instead of taking it.
- **Streaks grow it.** Three healthy days in a row advances the plant a stage,
  from `seed` all the way to `LEGENDARY`.
- **Nothing to install.** A stdlib-only Python script on your computer, a Worker in
  the cloud, Telegram as the UI. No account, no app, no pip.

```
   ten stages
   seed · sprout · sapling · young · mature · tree · blossom · cherry · ancient · LEGENDARY
```

## How it works

```
        machine                         cloud                    phone
  ┌───────────────────┐         ┌──────────────────────┐
  │  client/sprig.py  │         │  Cloudflare Worker   │
  │                   │  ping   │                      │
  │  probe idle time  ├────────►│  applyPing()         │
  │  active | away    │  /ping  │  plant state in KV   │
  └───────────────────┘         │                      │
                                │  cron 23:55 local    │
                                └──────────┬───────────┘
                                           │ daily report + events
                                           ▼
                                     Telegram chat
```

`src/plant.js` holds every rule as a pure function, so the day rollover is
testable. `handlers.js` does I/O and messages, `index.js` does routing. The
Worker is the only thing that decides what a plant looks like.

## Quick start

**1. Plant the cloud half**

```sh
git clone https://github.com/owarimono/sprig && cd sprig/worker
npx wrangler kv:namespace create PLANT_KV   # paste the id into wrangler.toml
npx wrangler secret put BOT_TOKEN           # from @BotFather
npx wrangler secret put AUTH_TOKEN          # any strong random string
npx wrangler secret put WEBHOOK_SECRET      # another one
npx wrangler deploy
```

**2. Point Telegram at it**

```sh
curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://<worker>.workers.dev/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

**3. Send `/start` to your bot**, then use that chat's id as `CHAT_ID` below.
`@userinfobot` prints it too.

**4. Run the client**

```sh
cd ../client
export WORKER_URL=https://<worker>.workers.dev
export AUTH_TOKEN=<the same string>
export CHAT_ID=<your chat id>

python3 sprig.py --dry-run   # which idle backend does this machine have?
python3 sprig.py             # start reporting
```

`--dry-run` checks detection and sends nothing. `--once` sends a single ping and
exits, which is all you need from a systemd timer or cron job.

## Commands

| Command | Effect |
| --- | --- |
| `/start` | Plant your first plant. Never overwrites an existing one. |
| `/status` | Health bar, stage, today's usage, streak. |
| `/limit <min>` | Daily budget, 5-720 minutes. |
| `/pause` | Freeze the plant while you travel or take a day off. |
| `/resume` | Resume counting. |
| `/reset` | Fresh seed. Streak and stage reset. |
| `/help` | Command list. |

The bot also speaks up on its own: at 25% health, on level up, on death, and
once a day with the full report.

## Idle detection

Probed in order, the first one that answers wins.

| Backend | Needs | Notes |
| --- | --- | --- |
| `logind` | systemd | Reads `IdleHint` and `IdleSinceHintMonotonic` over the system bus. Works on X11 **and** Wayland. |
| `xprintidle` | `xprintidle` | X11 and XWayland only. |
| `xssstate` | `xssstate` | X11 only. |
| `screensaver` | any `org.freedesktop.ScreenSaver` desktop | `GetActive` is a boolean, so idle time is only known as "at least the threshold". |

If no backend answers the client reports **nothing** rather than reporting
"active": a broken probe must never count every minute as screen time.

## Configuration

Client environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `WORKER_URL` | required | Worker base URL |
| `AUTH_TOKEN` | required | Shared secret, must match the Worker |
| `CHAT_ID` | required | Telegram chat to report to |
| `IDLE_THRESHOLD` | `300` | Seconds of inactivity that count as away |
| `PING_INTERVAL` | `60` | Seconds between pings. One active ping equals one minute of usage. |

Server settings, in `worker/wrangler.toml`:

| Setting | Meaning |
| --- | --- |
| `vars.TZ` | Timezone for the day boundary and the daily report. |
| `triggers.crons` | When the daily report fires. Cron is **always UTC**, so shift it to match `TZ`. |

Secrets never live in the repo. `BOT_TOKEN`, `AUTH_TOKEN` and `WEBHOOK_SECRET`
are read from the Worker environment.

## Development

```sh
cd worker
npm test                                       # node --test, no dependencies
npx wrangler deploy --dry-run --outdir dist    # bundle without deploying
npx wrangler dev --test-scheduled              # local Worker, fire the cron by hand
```

The suite covers day rollover, the limit and death rules, the pause freeze,
warning deduplication, old KV records and the timezone helper.

## Layout

```
client/sprig.py           idle detector and reporter, standard library only
worker/src/index.js       routes: /webhook, /ping, scheduled report
worker/src/handlers.js    Telegram commands, KV reads and writes
worker/src/plant.js       plant rules and message rendering, pure functions
worker/src/telegram.js    sendMessage wrapper
worker/test/plant.test.js node --test
```

## Notes

- One active ping equals one minute of usage. The client keeps a fixed cadence so
  the count stays honest even though pinging takes time.
- State is one KV record per chat, written on every ping. Two clients on the same
  chat could lose an update; there is one client per plant, so this is left alone.
- Killing the client stops the counting, which is the safe direction: the plant
  heals instead of dying while you are away from the machine.

---

<div align="center">
<sub>ISC licensed.</sub>
</div>
