"""Tests for the menu-bar usage logic — the fallback/cache behavior that has
regressed before (showing a misleading 100% instead of the real value)."""

import urllib.error

import claude_pulse.menubar as mb
import claude_pulse.data.limits as lim


# ── render_bar ────────────────────────────────────────────────────────────────

def test_render_bar_basic():
    assert mb.render_bar(0, 10) == "░" * 10 + " 0%"
    assert mb.render_bar(100, 10) == "█" * 10 + " 100%"
    assert mb.render_bar(50, 10) == "█" * 5 + "░" * 5 + " 50%"


def test_render_bar_clamps_out_of_range():
    assert mb.render_bar(150, 10).startswith("█" * 10)   # never overflows
    assert mb.render_bar(-5, 10).startswith("░")          # never negative


# ── current_usage: the source/fallback tiers ─────────────────────────────────

def test_recent_cache_is_served_without_fetching(monkeypatch):
    """A fresh cached value must be used directly — no endpoint call (avoids 429)."""
    monkeypatch.setattr(mb, "load_last_live_pct",
                        lambda max_age_seconds: 24.0 if max_age_seconds == mb.LIVE_CACHE_TTL else None)
    calls = {"n": 0}
    def spy(*a, **k):
        calls["n"] += 1
        return None
    monkeypatch.setattr(mb, "get_live_usage", spy)

    assert mb.current_usage(use_live=True) == (24.0, "live")
    assert calls["n"] == 0, "should not hit the endpoint when a fresh cache exists"


def test_successful_fetch_is_saved(monkeypatch):
    monkeypatch.setattr(mb, "load_last_live_pct", lambda max_age_seconds: None)
    monkeypatch.setattr(mb, "get_live_usage", lambda *a, **k: {"five_hour_pct": 31.0})
    saved = {}
    monkeypatch.setattr(mb, "save_last_live_pct", lambda p: saved.__setitem__("p", p))

    assert mb.current_usage(use_live=True) == (31.0, "live")
    assert saved["p"] == 31.0


def test_fetch_over_100_is_clamped(monkeypatch):
    monkeypatch.setattr(mb, "load_last_live_pct", lambda max_age_seconds: None)
    monkeypatch.setattr(mb, "get_live_usage", lambda *a, **k: {"five_hour_pct": 130.0})
    monkeypatch.setattr(mb, "save_last_live_pct", lambda p: None)

    pct, source = mb.current_usage(use_live=True)
    assert pct == 100 and source == "live"


def test_failed_fetch_uses_last_good_not_estimate(monkeypatch):
    """The key regression: a failed fetch must show the last real value, not 100%."""
    monkeypatch.setattr(mb, "load_last_live_pct",
                        lambda max_age_seconds: 24.0 if max_age_seconds == mb.LIVE_STALE_MAX else None)
    monkeypatch.setattr(mb, "get_live_usage", lambda *a, **k: None)
    # Estimate would say 100 — must NOT be used while a recent real value exists.
    monkeypatch.setattr(mb, "get_plan_usage", lambda plan: {"pct": 100.0})
    monkeypatch.setattr(mb, "load_saved_plan", lambda: "pro")

    assert mb.current_usage(use_live=True) == (24.0, "stale")


def test_estimate_only_when_no_live_value_exists(monkeypatch):
    monkeypatch.setattr(mb, "load_last_live_pct", lambda max_age_seconds: None)
    monkeypatch.setattr(mb, "get_live_usage", lambda *a, **k: None)
    monkeypatch.setattr(mb, "get_plan_usage", lambda plan: {"pct": 100.0})
    monkeypatch.setattr(mb, "load_saved_plan", lambda: "pro")

    assert mb.current_usage(use_live=True) == (100.0, "estimate")


# ── current_line: a fallback must be visibly marked ──────────────────────────

def test_line_marks_stale_and_estimate(monkeypatch):
    monkeypatch.setattr(mb, "current_usage", lambda use_live=True: (24.0, "stale"))
    assert mb.current_line().endswith(" ·")

    monkeypatch.setattr(mb, "current_usage", lambda use_live=True: (100.0, "estimate"))
    assert mb.current_line().endswith(" ≈")

    monkeypatch.setattr(mb, "current_usage", lambda use_live=True: (24.0, "live"))
    line = mb.current_line()
    assert "24%" in line and not line.endswith((" ·", " ≈"))


# ── limits: HTTP errors are classified, not lumped as "network" ──────────────

def _raise_http(code):
    def _f(_token):
        raise urllib.error.HTTPError("url", code, "err", {}, None)
    return _f


def test_429_is_rate_limited(monkeypatch):
    monkeypatch.setattr(lim, "_read_oauth", lambda: ({"accessToken": "x"}, "ok"))
    monkeypatch.setattr(lim, "_fetch", _raise_http(429))
    assert lim._fetch_usage() == (None, "rate_limited")


def test_401_is_expired(monkeypatch):
    monkeypatch.setattr(lim, "_read_oauth", lambda: ({"accessToken": "x"}, "ok"))
    monkeypatch.setattr(lim, "_fetch", _raise_http(401))
    assert lim._fetch_usage() == (None, "expired")


def test_other_http_is_network(monkeypatch):
    monkeypatch.setattr(lim, "_read_oauth", lambda: ({"accessToken": "x"}, "ok"))
    monkeypatch.setattr(lim, "_fetch", _raise_http(500))
    assert lim._fetch_usage() == (None, "network")
