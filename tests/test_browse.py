"""Tests for the sessions-browser parser."""

import json

from claude_pulse.data import browse
from claude_pulse.data.browse import (
    _clean_title,
    _extract_text,
    _is_real_prompt,
    _parse_session,
    list_sessions,
)


def test_extract_text_handles_string_and_blocks():
    assert _extract_text("hello") == "hello"
    assert _extract_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a b"
    assert _extract_text([{"type": "tool_result", "content": "x"}]) == ""


def test_clean_title_strips_image_marker_and_whitespace():
    assert _clean_title("[Image #1]  fix   the\n bug") == "fix the bug"
    assert _clean_title("plain prompt") == "plain prompt"


def test_is_real_prompt_rejects_harness_noise():
    assert _is_real_prompt("why is edge running in the background?")
    assert not _is_real_prompt("<local-command-caveat> ...")
    assert not _is_real_prompt("<command-name>foo</command-name>")
    assert not _is_real_prompt("")


def _write_session(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_parse_session_builds_summary(tmp_path):
    f = tmp_path / "abc123.jsonl"
    _write_session(f, [
        {"type": "user", "isMeta": True, "cwd": "C:/repos/Demo",
         "timestamp": "2026-06-01T10:00:00.000Z",
         "message": {"content": "<local-command-caveat>noise"}},
        {"type": "user", "cwd": "C:/repos/Demo",
         "timestamp": "2026-06-01T10:01:00.000Z",
         "message": {"content": "[Image #1] why is it slow?"}},
        {"type": "assistant", "timestamp": "2026-06-01T10:02:00.000Z",
         "message": {"model": "claude-opus-4-8", "content": []}},
    ])

    summary = _parse_session(f, str(tmp_path))
    assert summary is not None
    assert summary.session_id == "abc123"
    assert summary.cwd == "C:/repos/Demo"
    assert summary.project_name == "Demo"
    assert summary.title == "why is it slow?"        # meta + caveat skipped
    assert summary.message_count == 3
    assert "claude-opus-4-8" in summary.models
    assert summary.started_at.hour == 10


def test_parse_session_returns_none_for_empty(tmp_path):
    f = tmp_path / "empty.jsonl"
    f.write_text("\n\n", encoding="utf-8")
    assert _parse_session(f, str(tmp_path)) is None


def test_list_sessions_filters_by_window_and_project(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    old = projects / "C--repos-Old"
    new = projects / "C--repos-Fresh"
    old.mkdir(parents=True)
    new.mkdir(parents=True)

    _write_session(old / "old.jsonl", [
        {"type": "user", "cwd": "C:/repos/Old",
         "timestamp": "2000-01-01T00:00:00.000Z",
         "message": {"content": "ancient"}},
    ])
    _write_session(new / "fresh.jsonl", [
        {"type": "user", "cwd": "C:/repos/Fresh",
         "timestamp": "2026-06-12T00:00:00.000Z",
         "message": {"content": "recent work"}},
    ])

    monkeypatch.setattr(browse, "PROJECTS_DIR", projects)
    browse._summary_cache.clear()

    # 30-day window drops the year-2000 session.
    recent = list_sessions(days=30)
    ids = {s.session_id for s in recent}
    assert "fresh" in ids and "old" not in ids

    # Project filter narrows to a single match.
    assert {s.session_id for s in list_sessions(days=None, project="fresh")} == {"fresh"}
