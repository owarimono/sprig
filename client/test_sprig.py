#!/usr/bin/env python3
"""Checks for the sprig client. Run: python3 client/test_sprig.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sprig  # noqa: E402


def test_parse_env():
    text = """
# comment
WORKER_URL="https://example.workers.dev"
AUTH_TOKEN = abc123
CHAT_ID=-1002259919085

broken line without equals
"""
    assert sprig.parse_env(text) == {
        "WORKER_URL": "https://example.workers.dev",
        "AUTH_TOKEN": "abc123",
        "CHAT_ID": "-1002259919085",
    }
    assert sprig.parse_env("") == {}


def test_config_precedence():
    # Defaults lose to the file, the file loses to the environment.
    path = Path("/tmp/sprig-test-env")
    path.write_text('PING_INTERVAL="30"\nIDLE_THRESHOLD="120"\n')
    real_path = sprig.CONFIG_PATH
    sprig.CONFIG_PATH = path
    os.environ.pop("PING_INTERVAL", None)
    try:
        config = sprig.load_config()
        assert config["PING_INTERVAL"] == "30"
        assert config["IDLE_THRESHOLD"] == "120"
        assert config["CHAT_ID"] == ""  # absent, and no KeyError
        os.environ["PING_INTERVAL"] = "99"
        assert sprig.load_config()["PING_INTERVAL"] == "99"
    finally:
        os.environ.pop("PING_INTERVAL", None)
        sprig.CONFIG_PATH = real_path
        path.unlink()


def test_unit_is_systemd_shaped():
    unit = sprig.unit_text()
    assert "[Service]" in unit and "[Install]" in unit
    assert "EnvironmentFile=" in unit
    assert "Restart=always" in unit
    assert "WantedBy=default.target" in unit


def test_render_line_tolerates_missing_state():
    line = sprig.render_line("12:00:00", "logind", 0, "active", None)
    assert "active" in line and "logind" in line and "[" not in line

    state = {"health": 50, "active_minutes_today": 15, "limit_min": 30,
             "plant_alive": True, "paused": False}
    line = sprig.render_line("12:00:00", "logind", 0, "active", state)
    assert "50%" in line and "today 15/30 min" in line

    dead = dict(state, plant_alive=False)
    assert "died" in sprig.render_line("12:00:00", "logind", 9, "active", dead)


def test_bar_bounds():
    assert sprig.bar(100) == "█" * 16
    assert sprig.bar(0) == "░" * 16
    assert sprig.bar(-5) == "░" * 16 and sprig.bar(140) == "█" * 16


if __name__ == "__main__":
    checks = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"{len(checks)} client checks passed")
