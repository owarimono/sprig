#!/usr/bin/env python3
"""
Sprig - client.

Reports how long this machine has been in use to the Sprig Worker, which
grows or kills a plant in your Telegram chat. Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

IDLE_THRESHOLD = int(os.environ.get("IDLE_THRESHOLD", 300))  # seconds idle => away
PING_INTERVAL = int(os.environ.get("PING_INTERVAL", 60))


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


def _probe_logind():
    """systemd-logind: works on X11 and Wayland, nothing to install."""
    if "boolean true" not in _logind_prop("IdleHint"):
        return 0
    for line in _logind_prop("IdleSinceHintMonotonic").splitlines():
        if "uint64" in line:
            since_usec = int(line.split()[-1])
            if since_usec:
                now_usec = time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000
                return max(0, int((now_usec - since_usec) / 1_000_000))
    return IDLE_THRESHOLD  # idle according to logind, duration unknown


def _probe_xprintidle():
    return int(subprocess.check_output(["xprintidle"], timeout=5).strip()) // 1000


def _probe_xssstate():
    return int(subprocess.check_output(["xssstate", "-i"], timeout=5).strip()) // 1000


def _probe_screensaver():
    """Boolean only: active or (assumed) away. Coarse last resort.

    KDE Plasma 6 dropped org.kde.screensaver.GetIdleTime, so the old probe path
    is gone; only GetActive survives.
    """
    out = _dbus("--session", "--dest=org.freedesktop.ScreenSaver",
                "/ScreenSaver", "org.freedesktop.ScreenSaver.GetActive")
    return IDLE_THRESHOLD if "boolean true" in out else 0


PROBES = (
    ("logind", _probe_logind),
    ("xprintidle", _probe_xprintidle),
    ("xssstate", _probe_xssstate),
    ("screensaver", _probe_screensaver),
)


def detect_idle():
    """Idle seconds, or (None, None) if no backend works.

    Unknown is deliberately not reported as active: a broken probe would
    otherwise count every minute as usage and kill the plant.
    """
    for name, probe in PROBES:
        try:
            secs = probe()
        except Exception:
            continue
        if secs is not None:
            return secs, name
    return None, None


def ping(url, token, chat_id, status, idle):
    body = json.dumps({
        "token": token,
        "chat_id": chat_id,
        "status": status,
        "idle_seconds": idle,
    }).encode()
    req = Request(f"{url}/ping", data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except HTTPError as err:
        return False, f"HTTP {err.code}"
    except URLError as err:
        return False, f"network: {err.reason}"


def main():
    ap = argparse.ArgumentParser(description="Report computer usage to Sprig.")
    ap.add_argument("--once", action="store_true", help="send a single ping and exit")
    ap.add_argument("--dry-run", action="store_true", help="print status, send nothing")
    args = ap.parse_args()

    url = os.environ.get("WORKER_URL", "").rstrip("/")
    token = os.environ.get("AUTH_TOKEN", "")
    chat_id = os.environ.get("CHAT_ID", "")

    if args.dry_run:
        idle, backend = detect_idle()
        print("~ Sprig (dry run) ~")
        print(f"idle backend: {backend or 'none'}")
        print(f"idle: {idle}s  => {'idle' if idle and idle >= IDLE_THRESHOLD else 'active'}"
              if idle is not None else "idle: unknown, nothing would be reported")
        return

    if not all([url, token, chat_id]):
        sys.exit("Set WORKER_URL, AUTH_TOKEN and CHAT_ID environment variables.")

    print("~ Sprig ~")
    print(f"away after {IDLE_THRESHOLD}s idle, ping every {PING_INTERVAL}s")
    print("Ctrl+C to stop\n")

    # Fixed-cadence loop: the ping itself takes time, so sleep the remainder of
    # each window instead of a flat interval. One minute of usage == one ping.
    next_tick = time.monotonic()
    while True:
        next_tick += PING_INTERVAL
        idle, backend = detect_idle()
        if idle is None:
            print("  no idle backend available (need xprintidle, KDE dbus or xssstate)")
        else:
            status = "idle" if idle >= IDLE_THRESHOLD else "active"
            icon = "(n_n)" if status == "idle" else "(o_o)"
            ok, detail = ping(url, token, chat_id, status, idle)
            mark = "ok" if ok else detail
            print(f"  [{time.strftime('%H:%M:%S')}] {backend} idle={idle}s "
                  f"status={status} {icon} {mark}")
            if detail == "HTTP 401":
                sys.exit("Worker rejected AUTH_TOKEN - check the secret.")

        if args.once:
            return
        time.sleep(max(0, next_tick - time.monotonic()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n(´-ω-)zzz bye")
