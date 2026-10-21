<div align="center">

<img src="assets/tree.svg" width="88" height="88" alt="Sprig">

# Sprig

**Grow a plant by staying off your computer.**

Stay inside your daily screen-time budget and it levels up.
Walk away and it heals. Go over the limit and it dies.

<p align="center">
  <a href="https://workers.cloudflare.com/"><img alt="Platform: Cloudflare Workers" src="https://img.shields.io/badge/Platform-Cloudflare_Workers-34D399?style=for-the-badge&labelColor=022C22&logo=cloudflareworkers&logoColor=white"></a>
  <img alt="Client: Python 3.8+ stdlib" src="https://img.shields.io/badge/Client-Python_3.8+_stdlib-10B981?style=for-the-badge&labelColor=022C22&logo=python&logoColor=white">
  <img alt="Store: Workers KV" src="https://img.shields.io/badge/Store-Workers_KV-059669?style=for-the-badge&labelColor=022C22">
  <img alt="Ping: once a minute" src="https://img.shields.io/badge/Ping-1_min-047857?style=for-the-badge&labelColor=022C22">
  <img alt="License: ISC" src="https://img.shields.io/badge/License-ISC-6EE7B7?style=for-the-badge&labelColor=022C22">
  <img alt="Release: v1.2.1" src="https://img.shields.io/badge/Release-v1.2.1-A7F3D0?style=for-the-badge&labelColor=022C22">
</p>

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

## Setup

Two halves: one small program in the cloud (Cloudflare, free) and one on the
computer you want to track. Follow the steps in order. Each one ends with a
**you should see** line — if you do not see it, stop there and read
[If something went wrong](#if-something-went-wrong).

No coding involved. It is copy-paste, four accounts-free clicks, and about
fifteen minutes.

**You need:** a Telegram account, a free Cloudflare account, and a Linux
computer. The tracking half talks to `systemd`, so it is Linux-only; the cloud
half runs from any OS.

### 1. Make the bot

In Telegram, search for **@BotFather** and press Start. Send `/newbot`. It asks
for a display name (anything) and a username, which must end in `bot` — for
example `my_sprig_bot`.

It replies with a token that looks like `7123456789:AAH8k...`.

> **Keep it secret.** That token is the bot's password — anyone who has it
> controls your bot. Leave this chat open, you need the token in steps 7 and 9.

### 2. Get the code

Open <https://github.com/owarimono/sprig>, click the green **Code** button, then
**Download ZIP**. Unzip it — you get a folder named `sprig-main`.

**You should see:** `sprig-main` containing `README.md`, `client/`, `worker/`.

### 3. Open a terminal

On Linux press <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>T</kbd>. A black window with
a blinking cursor appears. Everything below is typed there, one line at a time,
then <kbd>Enter</kbd>.

To paste, use <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd> (`Ctrl+V` does not
work in a terminal).

Point the terminal at the folder from step 2 — type `cd ` (with the space), then
drag the unzipped folder from your file manager onto the terminal window, then
press <kbd>Enter</kbd>:

```sh
cd /home/you/Downloads/sprig-main
ls
```

**You should see:** `README.md  client  worker`.

### 4. Install Node.js

The cloud half is built with it. Check first:

```sh
node -v
```

**You should see:** something like `v20.11.0`. Anything 18 or newer is fine.

If it says *command not found*, install it and try again:

```sh
sudo pacman -S nodejs npm      # Arch
sudo apt install nodejs npm    # Debian, Ubuntu
sudo dnf install nodejs        # Fedora
```

### 5. Log in to Cloudflare

Create a free account at <https://dash.cloudflare.com/sign-up> first. Then:

```sh
cd worker
npx wrangler login
```

The first run asks *Need to install the following packages… Ok to proceed?* —
type `y` and press <kbd>Enter</kbd>. A browser window opens; click **Allow**.

```sh
npx wrangler whoami
```

**You should see:** your Cloudflare email address.

### 6. Create the storage

The Worker keeps every plant in a key-value store named `PLANT_KV`.

```sh
npx wrangler kv namespace create PLANT_KV
```

**You should see:** a line like `id = "0f2a9c1b4d..."`. Copy that id.

Now open `worker/wrangler.toml` in any text editor (double-clicking it opens one
on most desktops), find the line `id = "YOUR_KV_NAMESPACE_ID"`, and replace only
the part inside the quotes with the id you copied. Save the file. The line
should end up looking like `id = "0f2a9c1b4d..."`.

### 7. Store the three secrets

Each command asks for a value and hides it while you paste — no characters
appear. That is normal. Press <kbd>Enter</kbd> after pasting.

```sh
npx wrangler secret put BOT_TOKEN
```

Paste the token from step 1.

```sh
python3 -c "import secrets; print(secrets.token_hex(24))"   # prints a random string
npx wrangler secret put AUTH_TOKEN
```

Paste the random string it printed. **Write this one down** — the client on your
computer needs it in step 11.

```sh
python3 -c "import secrets; print(secrets.token_hex(24))"
npx wrangler secret put WEBHOOK_SECRET
```

Paste the second random string. Write it down too, step 9 needs it.

**You should see:** `Success! Uploaded secret BOT_TOKEN`, once per secret.

### 8. Deploy

```sh
npx wrangler deploy
```

**You should see:** a line like
`https://sprig.your-name.workers.dev`. That is your Worker's address. Copy it —
steps 9 and 11 need it, without a trailing slash.

### 9. Connect Telegram to the Worker

Telegram has to be told where to deliver your messages. Replace the three
placeholders — including the `<` and `>` — and run it as one line:

```sh
curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=<WORKER_URL>/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

**You should see:** `{"ok":true,"result":true,"description":"Webhook was set"}`.

### 10. Get your chat id

Open your bot in Telegram (BotFather gives you the link) and send `/start`.

**You should see:** a welcome message and `Your plant has been planted!`

Now message **@userinfobot** — it replies with a line like `Id: 123456789`. That
number is your chat id. For a group chat instead, add @userinfobot to the group
and it prints the group id, which starts with `-`.

### 11. Install the tracker

This is the half that lives on your computer. It starts itself at login and
needs nothing after this step.

```sh
cd ../client
python3 sprig.py install \
  --worker-url https://sprig.your-name.workers.dev \
  --token <AUTH_TOKEN> \
  --chat-id <CHAT_ID>
```

**You should see:** `sprig.service` reported as `enabled and running`, then one
status line with a health bar. That line is a real ping — the Worker already
answered.

```sh
sprig status
sprig logs
```

`status` says `active (running)`; `logs` shows one line per change instead of
spam.

### 12. Check it

Send `/status` to your bot. It answers with the plant, the health bar, today's
minutes and the streak. Leave the computer for ten minutes and watch the bar go
up.

## If something went wrong

| What you see | What it means |
| --- | --- |
| `401` or `Worker rejected AUTH_TOKEN` | The token in the install command is not the one stored in step 7. Run step 11 again with the correct `AUTH_TOKEN`. |
| `{"ok":false,...}` from step 9 | The bot token is wrong, or the URL does not end in `/webhook`. |
| Bot never answers `/start` | The webhook is not set. Run `curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"` — `url` must be your Worker address plus `/webhook`. |
| `npx: command not found` | Node.js is missing or too old — step 4. |
| `no idle backend available` | The client cannot read idle time. It needs a real systemd login session; a bare SSH shell or a container has none. |
| `IDLE_THRESHOLD must be a positive integer` | A typo in `~/.config/sprig/env`. Fix the number, then `sprig restart`-style reload: `systemctl --user restart sprig`. |
| The service restarts in a loop | `sprig logs` now prints the reason instead of dying silently. |

Never paste a token into an issue, a screenshot or a chat. If one leaked, send
`/revoke` to @BotFather to replace the bot token and repeat steps 7 and 9.

## Commands

| Command | Effect |
| --- | --- |
| `/start` | Plant your first plant. Never overwrites an existing one. |
| `/status` | Health bar, stage, today's usage, streak. |
| `/limit <min>` | Daily budget, 5-720 minutes. Lowering it below today's usage can kill the plant. |
| `/pause` | Freeze the plant while you travel or take a day off. |
| `/resume` | Resume counting. |
| `/reset` | Fresh seed. Streak and stage reset. |
| `/help` | Command list. |

The bot also speaks up on its own: at 25% health, on level up, on death, and
once a day with the full report.

## The `sprig` command

Installing drops a `sprig` command into `~/.local/bin`. It reads
`~/.config/sprig/env`, which the environment can still override.

| Command | Effect |
| --- | --- |
| `sprig` | Run in the foreground and show a live status line. |
| `sprig install [--worker-url U] [--token T] [--chat-id ID] [--idle-threshold S]` | Write the config and unit, link the command, start the service. `--dry-run` prints everything and touches nothing. |
| `sprig status` | Service status. |
| `sprig logs [-f]` | Last 40 journal lines, `-f` to follow. |
| `sprig uninstall` | Stop and remove the service and the command. Keeps the config. |
| `sprig run --once` | One ping, then exit. |
| `sprig run --dry-run` | Report which idle backend works, send nothing. |

Running in the foreground rewrites one line in place:

```
~ Sprig ~
away after 300s idle, ping every 60s. Ctrl+C to stop.

  21:08:11  active  (o_o)  logind idle=0s  [██████████████░░]  90%  today 3/30 min
```

Under systemd there is no TTY, so the client logs a line only when something
changes instead of writing 1440 identical lines a day into the journal. The
health bar and the minute count come back from the Worker on every ping.

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

cd ..
python3 client/test_sprig.py                   # client checks, no dependencies
python3 client/sprig.py run --dry-run          # which idle backend works here?
```

The Worker suite covers day rollover, the limit and death rules, the pause freeze,
warning deduplication, old KV records, the timezone helper, gap days, KV page
walking and the no-op write skip. The client checks cover config parsing and
precedence, rejected numeric settings, the generated unit file and status-line
rendering.

## Layout

```
client/sprig.py           idle detector, reporter and the `sprig` command itself
client/test_sprig.py      checks for config parsing, the unit file and rendering
worker/src/index.js       routes: /webhook, /ping, scheduled report
worker/src/handlers.js    Telegram commands, KV reads and writes
worker/src/plant.js       plant rules and message rendering, pure functions
worker/src/telegram.js    sendMessage wrapper
worker/test/plant.test.js rules: rollover, health, death, gaps
worker/test/handlers.test.js commands, KV paging, write skipping
```

## Notes

- One active ping equals one minute of usage. The client keeps a fixed cadence so
  the count stays honest even though pinging takes time.
- State is one KV record per chat, and it is written only when the record really
  changes: a paused ping, or an idle ping at full health, writes nothing. One ping
  a minute is 1440 writes a day, and the free tier allows 1000.
- Two clients on the same chat could lose an update; there is one client per
  plant, so this is left alone.
- Killing the client stops the counting, which is the safe direction: the plant
  heals instead of dying while you are away from the machine.
- Days with no pings at all are not graded. Only the day immediately before today
  is settled, so a weekend with the laptop off, or a long `/pause`, earns no
  streak day instead of one free one.

---

<div align="center">
<sub>ISC licensed.</sub>
</div>
