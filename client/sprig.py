#!/usr/bin/env python3
"""Sprig - client.

Reports how long this machine has been in use to the Sprig Worker, which grows
or kills a plant in your Telegram chat. Standard library only.

  sprig install --worker-url URL --token TOKEN --chat-id ID
  sprig status | logs [-f] | uninstall
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_PATH = Path(os.environ.get("SPRIG_CONFIG", "~/.config/sprig/env")).expanduser()
UNIT_PATH = Path(os.environ.get("SPRIG_UNIT", "~/.config/systemd/user/sprig.service")).expanduser()
BIN_PATH = Path(os.environ.get("SPRIG_BIN", "~/.local/bin/sprig")).expanduser()
SERVICE = "sprig.service"

DEFAULTS = {"IDLE_THRESHOLD": "300", "PING_INTERVAL": "60"}
REQUIRED = ("WORKER_URL", "AUTH_TOKEN", "CHAT_ID")

UNIT_TEMPLATE = """[Unit]
Description=Sprig usage reporter
After=graphical-session.target

[Service]
Type=simple
EnvironmentFile={config}
ExecStart={python} {script}
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""

# The script is standard library only, so pin the system interpreter: a venv
# path would break the unit the day that venv is deleted.
PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable


# ---------------------------------------------------------------- configuration

def parse_env(text):
    """Parse a shell-style KEY=value file. Comments and blanks are skipped."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config():
    """Defaults, then the config file, then the environment."""
    config = {**{key: "" for key in REQUIRED}, **DEFAULTS}
    if CONFIG_PATH.exists():
        config.update(parse_env(CONFIG_PATH.read_text()))
    for key in list(DEFAULTS) + list(REQUIRED):
        if os.environ.get(key):
            config[key] = os.environ[key]
    config["WORKER_URL"] = config.get("WORKER_URL", "").rstrip("/")
    return config


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f'{key}="{value}"\n' for key, value in sorted(config.items()))
    CONFIG_PATH.write_text(
        "# Sprig client configuration. Read by `sprig` and by systemd.\n" + body)
    CONFIG_PATH.chmod(0o600)


def unit_text():
    return UNIT_TEMPLATE.format(
        config=CONFIG_PATH, python=PYTHON, script=Path(__file__).resolve())


def systemctl(*args, **kwargs):
    """Run systemctl --user. Returns (ok, message); never raises."""
    try:
        done = subprocess.run(["systemctl", "--user", *args],
                              capture_output=True, text=True, **kwargs)
    except FileNotFoundError:
        return False, "systemctl not found (not a systemd machine?)"
    if done.returncode:
        return False, done.stderr.strip() or done.stdout.strip()
    return True, done.stdout.strip()


# ------------------------------------------------------------- idle detection

def _dbus(*args):
    return subprocess.check_output(["dbus-send", "--print-reply", *args],
                                   timeout=5, text=True)


def _logind_prop(prop):
    return _dbus(
        "--system", "--dest=org.freedesktop.login1",
        "/org/freedesktop/login1/session/auto",
        "org.freedesktop.DBus.Properties.Get",
        "string:org.freedesktop.login1.Session", f"string:{prop}",
    )


def _probe_logind(threshold):
    """systemd-logind: works on X11 and Wayland, nothing to install."""
    if "boolean true" not in _logind_prop("IdleHint"):
        return 0
    for line in _logind_prop("IdleSinceHintMonotonic").splitlines():
        if "uint64" in line:
            since_usec = int(line.split()[-1])
            if since_usec:
                now_usec = time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000
                return max(0, int((now_usec - since_usec) / 1_000_000))
    return threshold  # idle according to logind, duration unknown


def _probe_xprintidle(_threshold):
    return int(subprocess.check_output(["xprintidle"], timeout=5).strip()) // 1000


def _probe_xssstate(_threshold):
    return int(subprocess.check_output(["xssstate", "-i"], timeout=5).strip()) // 1000


def _probe_screensaver(threshold):
    """Boolean only: active or (assumed) away. Coarse last resort.

    KDE Plasma 6 dropped org.kde.screensaver.GetIdleTime, so that path is gone
    and only GetActive survives.
    """
    out = _dbus("--session", "--dest=org.freedesktop.ScreenSaver",
                "/ScreenSaver", "org.freedesktop.ScreenSaver.GetActive")
    return threshold if "boolean true" in out else 0


PROBES = (
    ("logind", _probe_logind),
    ("xprintidle", _probe_xprintidle),
    ("xssstate", _probe_xssstate),
    ("screensaver", _probe_screensaver),
)


def detect_idle(threshold):
    """Idle seconds, or (None, None) if no backend works.

    Unknown is deliberately not reported as active: a broken probe would
    otherwise count every minute as usage and kill the plant.
    """
    for name, probe in PROBES:
        try:
            secs = probe(threshold)
        except Exception:
            continue
        if secs is not None:
            return secs, name
    return None, None


# --------------------------------------------------------------------- worker

def ping(url, token, chat_id, status, idle):
    """Returns (ok, detail, plant_state_or_None)."""
    body = json.dumps({
        "token": token,
        "chat_id": chat_id,
        "status": status,
        "idle_seconds": idle,
    }).encode()
    req = Request(f"{url}/ping", data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read()
            try:
                return True, f"HTTP {resp.status}", json.loads(raw)
            except ValueError:
                return True, f"HTTP {resp.status}", None
    except HTTPError as err:
        return False, f"HTTP {err.code}", None
    except URLError as err:
        return False, f"network: {err.reason}", None


# ------------------------------------------------------------------------ ui

def bar(pct, width=16):
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def render_line(when, backend, idle, status, state):
    """One status line. Tolerates a server that sends no state."""
    icon = {"idle": "(n_n)", "active": "(o_o)", "paused": "(-_-)"}.get(status, "(._.)")
    parts = [when, f"{status:<6}", icon, f"{backend} idle={idle}s"]
    if state:
        health = state.get("health", 100)
        parts.append(f"[{bar(health)}] {health:>3}%")
        parts.append(f"today {state.get('active_minutes_today', 0)}/{state.get('limit_min', 30)} min")
        if not state.get("plant_alive", True):
            parts[-1] += "  (;.;) plant died"
        elif state.get("paused"):
            parts[-1] += "  paused"
    return "  " + "  ".join(parts)


def colour(text, status):
    if not sys.stdout.isatty():
        return text
    codes = {"idle": "32", "active": "33", "paused": "36"}
    return f"\033[{codes.get(status, '0')}m{text}\033[0m"


# ------------------------------------------------------------------- commands

def _positive_int(value):
    """Env files are hand-edited: a typo must be a message, not a traceback."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def cmd_run(args):
    config = load_config()
    threshold = _positive_int(config.get("IDLE_THRESHOLD"))
    interval = _positive_int(config.get("PING_INTERVAL"))
    if not threshold or not interval:
        print("IDLE_THRESHOLD and PING_INTERVAL must be positive integers "
              f"(got {config.get('IDLE_THRESHOLD')!r} and {config.get('PING_INTERVAL')!r}).",
              file=sys.stderr)
        return 1

    if args.dry_run:
        idle, backend = detect_idle(threshold)
        print("~ Sprig (dry run) ~")
        print(f"config:  {CONFIG_PATH}{'' if CONFIG_PATH.exists() else '  (missing)'}")
        print(f"backend: {backend or 'none'}")
        if idle is None:
            print("idle:    unknown, nothing would be reported")
        else:
            status = "idle" if idle >= threshold else "active"
            print(f"idle:    {idle}s  => {status}")
        return 0

    missing = [key for key in REQUIRED if not config.get(key)]
    if missing:
        print(f"Missing {', '.join(missing)}.", file=sys.stderr)
        print("Run: sprig install --worker-url URL --token TOKEN --chat-id ID", file=sys.stderr)
        return 1

    url, token, chat_id = (config[k] for k in REQUIRED)
    tty = sys.stdout.isatty()
    if tty:
        print("~ Sprig ~")
        print(f"away after {threshold}s idle, ping every {interval}s. Ctrl+C to stop.\n")

    # Fixed-cadence loop: the ping itself takes time, so sleep the remainder of
    # each window. One active ping equals one minute of usage.
    next_tick = time.monotonic()
    previous = None
    while True:
        next_tick += interval
        idle, backend = detect_idle(threshold)
        if idle is None:
            line = "  no idle backend available (need logind, xprintidle or xssstate)"
            if tty or line != previous:
                print(line, file=sys.stderr)
            previous = line
        else:
            status = "idle" if idle >= threshold else "active"
            ok, detail, state = ping(url, token, chat_id, status, idle)
            if not ok and detail == "HTTP 401":
                print("Worker rejected AUTH_TOKEN - check the secret.", file=sys.stderr)
                return 1
            line = render_line(time.strftime("%H:%M:%S"), backend, idle, status, state)
            if not ok:
                line += f"  {detail}"

            # Interactive: rewrite one line. Under systemd: log changes only, so
            # the journal does not collect 1440 identical lines a day.
            if tty:
                print("\r" + colour(line, status) + " " * 8, end="", flush=True)
            elif line != previous:
                print(line, flush=True)
            previous = line

        if args.once:
            if tty:
                print()
            return 0
        now = time.monotonic()
        if next_tick <= now:
            # The ping overran its slot. Skip the missed window instead of
            # sleeping 0s forever, which used to spin the loop at full speed.
            next_tick = now + interval
        time.sleep(max(0, next_tick - now))


def cmd_install(args):
    config = load_config()
    for key, value in (("WORKER_URL", args.worker_url), ("AUTH_TOKEN", args.token),
                       ("CHAT_ID", args.chat_id),
                       ("IDLE_THRESHOLD", args.idle_threshold)):
        if value:
            config[key] = value

    for key in REQUIRED:
        if not config.get(key):
            print(f"--{key.lower().replace('_', '-')} is required.", file=sys.stderr)
            return 1
    config["WORKER_URL"] = config["WORKER_URL"].rstrip("/")
    if not config["WORKER_URL"].startswith("http"):
        print("WORKER_URL must start with http:// or https://", file=sys.stderr)
        return 1
    try:
        int(config["CHAT_ID"])  # group ids are negative
    except ValueError:
        print("CHAT_ID must be numeric. Ask @userinfobot, or use the id /start replies with.",
              file=sys.stderr)
        return 1
    for key in DEFAULTS:
        if not _positive_int(config.get(key)):
            print(f"{key} must be a positive integer, got {config.get(key)!r}.", file=sys.stderr)
            return 1
    if any(character in config["AUTH_TOKEN"] for character in '"\'\\\n\r'):
        print("AUTH_TOKEN must not contain quotes, backslashes or newlines.",
              file=sys.stderr)
        return 1

    keys = {key: config.get(key, DEFAULTS.get(key, ""))
            for key in (*REQUIRED, *DEFAULTS)}
    if args.dry_run:
        print("--- " + str(CONFIG_PATH) + " (mode 600) ---")
        print("".join(f'{k}="{v}"\n' for k, v in sorted(keys.items())), end="")
        print("--- " + str(UNIT_PATH) + " ---")
        print(unit_text().format(config=CONFIG_PATH))
        print("--- " + str(BIN_PATH) + " -> " + str(Path(__file__).resolve()) + " ---")
        return 0

    save_config(keys)
    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(unit_text())
    BIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if BIN_PATH.is_symlink() or BIN_PATH.exists():
        BIN_PATH.unlink()
    BIN_PATH.symlink_to(Path(__file__).resolve())
    os.chmod(Path(__file__).resolve(), 0o755)

    for command in (["daemon-reload"], ["enable", "--now", SERVICE]):
        ok, message = systemctl(*command)
        if not ok:
            print(f"systemctl --user {' '.join(command)} failed: {message}", file=sys.stderr)
            print("\nFiles were written anyway. Fix the error and run:\n"
                  f"  systemctl --user enable --now {SERVICE}", file=sys.stderr)
            return 1

    print(f"Config   {CONFIG_PATH}")
    print(f"Unit     {UNIT_PATH}")
    print(f"Command  {BIN_PATH}")
    print(f"Service  {SERVICE} enabled and running\n")

    idle, backend = detect_idle(int(config["IDLE_THRESHOLD"]))
    print(f"Idle backend: {backend or 'none found'}")
    ok, detail, state = ping(config["WORKER_URL"], config["AUTH_TOKEN"],
                             int(config["CHAT_ID"]), "idle", idle or 0)
    if not ok:
        print(f"Worker said: {detail} - check WORKER_URL and AUTH_TOKEN.")
        return 1
    print(f"Worker said: {detail}, plant at {state.get('health', '?')}% "
          f"({state.get('stage', '?')})" if state else f"Worker said: {detail}")
    print(f"\nCheck on it with: sprig status, sprig logs -f")
    return 0


def cmd_uninstall(_args):
    systemctl("disable", "--now", SERVICE)
    for path in (UNIT_PATH, BIN_PATH):
        if path.is_symlink() or path.exists():
            path.unlink()
            print(f"removed {path}")
    systemctl("daemon-reload")
    print(f"kept {CONFIG_PATH} (delete it to forget the credentials)")
    return 0


def _run(command):
    """Run a system tool with its output attached; a missing tool is a message."""
    try:
        return subprocess.run(command).returncode
    except FileNotFoundError:
        print(f"{command[0]} not found (not a systemd machine?)", file=sys.stderr)
        return 1


def cmd_status(_args):
    return _run(["systemctl", "--user", "status", SERVICE, "--no-pager"])


def cmd_logs(args):
    command = ["journalctl", "--user", "-u", SERVICE, "-n", "40", "--no-pager", "-o", "cat"]
    if args.follow:
        command.append("-f")
    return _run(command)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="sprig", description="Grow a plant by staying off your computer.")
    sub = ap.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="report usage in the foreground (default)")
    run.add_argument("--once", action="store_true", help="send one ping and exit")
    run.add_argument("--dry-run", action="store_true", help="show what would be sent")

    install = sub.add_parser("install", help=f"write config, install the {SERVICE} user service")
    install.add_argument("--worker-url", help="Worker base URL")
    install.add_argument("--token", help="shared AUTH_TOKEN")
    install.add_argument("--chat-id", help="Telegram chat id to report to")
    install.add_argument("--idle-threshold", help="seconds idle that count as away")
    install.add_argument("--dry-run", action="store_true", help="print the files, touch nothing")

    sub.add_parser("uninstall", help="remove the service and the sprig command")
    sub.add_parser("status", help="service status")
    logs = sub.add_parser("logs", help="recent service logs")
    logs.add_argument("-f", "--follow", action="store_true", help="follow the log")

    ap.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    handlers = {"run": cmd_run, "install": cmd_install, "uninstall": cmd_uninstall,
                "status": cmd_status, "logs": cmd_logs}
    return handlers[args.cmd or "run"](args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n(´-ω-)zzz bye")
