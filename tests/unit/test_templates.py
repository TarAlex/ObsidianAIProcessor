"""tests/unit/test_templates.py — unit tests for agent.vault.templates.

All template fixtures are written to pytest's tmp_path; no real vault needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import agent.vault.templates as tmpl_mod
from agent.vault.templates import get_template_path, render_template


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(directory: Path, name: str, content: str) -> Path:
    """Write a template fixture file and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


# ── test 1: domain_index.md renders domain variable ──────────────────────────

def test_render_domain_index(tmp_path):
    tdir = tmp_path / "templates"
    _write(tdir, "domain_index.md", "# {{ domain | title }}\n\nWelcome to {{ domain }}.\n")
    result = render_template("domain_index.md", {"domain": "engineering"}, tdir)
    assert "# Engineering" in result
    assert "Welcome to engineering." in result


# ── test 2: subdomain_index.md renders all three vars ────────────────────────

def test_render_subdomain_index(tmp_path):
    tdir = tmp_path / "templates"
    _write(
        tdir,
        "subdomain_index.md",
        "# {{ subdomain | title }}\n"
        "> Sub of [[{{ domain_path }}]].\n"
        "Domain: {{ domain }}\n",
    )
    result = render_template(
        "subdomain_index.md",
        {"domain": "engineering", "subdomain": "python", "domain_path": "engineering/python"},
        tdir,
    )
    assert "# Python" in result
    assert "[[engineering/python]]" in result
    assert "Domain: engineering" in result


# ── test 3: None optional var renders empty string, no exception ──────────────

def test_render_none_optional_var_no_crash(tmp_path):
    tdir = tmp_path / "templates"
    _write(tdir, "subdomain_index.md", "Sub: {{ subdomain }}\nDomain: {{ domain }}\n")
    # subdomain=None should not raise; Jinja2 Undefined renders as ''
    result = render_template(
        "subdomain_index.md",
        {"domain": "engineering", "subdomain": None},
        tdir,
    )
    assert "Domain: engineering" in result
    # None value should not crash; rendered as empty or 'None'
    # (Jinja2 renders None as the string 'None' via str() — acceptable; key point is no exception)
    assert "Sub:" in result


# ── test 4: template not found → FileNotFoundError with name in message ───────

def test_template_not_found_raises(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    with pytest.raises(FileNotFoundError) as exc_info:
        render_template("nonexistent.md", {}, tdir)
    assert "nonexistent.md" in str(exc_info.value)


# ── test 5: template_dir does not exist → FileNotFoundError ──────────────────

def test_template_dir_missing_raises(tmp_path):
    missing_dir = tmp_path / "no_such_dir"
    with pytest.raises(FileNotFoundError) as exc_info:
        render_template("any.md", {}, missing_dir)
    assert str(missing_dir) in str(exc_info.value)


# ── test 6: _ENV_CACHE has exactly one entry after two calls to same dir ──────

def test_env_cache_single_entry_per_dir(tmp_path):
    tdir = tmp_path / "templates"
    _write(tdir, "domain_index.md", "Hello {{ domain }}\n")

    # Clear the module-level cache before this test to get a clean baseline.
    tmpl_mod._ENV_CACHE.clear()

    render_template("domain_index.md", {"domain": "a"}, tdir)
    render_template("domain_index.md", {"domain": "b"}, tdir)

    assert len(tmpl_mod._ENV_CACHE) == 1


# ── test 7: get_template_path returns correct path ───────────────────────────

def test_get_template_path(tmp_path):
    result = get_template_path(tmp_path)
    assert result == tmp_path / "_AI_META" / "templates"


# ── test 8: autoescape=False — <br> tag passes through unescaped ──────────────

def test_autoescape_off_html_passthrough(tmp_path):
    tdir = tmp_path / "templates"
    _write(tdir, "html.md", "Line one.<br>Line two.\n")
    result = render_template("html.md", {}, tdir)
    assert "<br>" in result
    assert "&lt;br&gt;" not in result


# ── test 9: keep_trailing_newline=True — trailing newline preserved ───────────

def test_keep_trailing_newline(tmp_path):
    tdir = tmp_path / "templates"
    _write(tdir, "trail.md", "Some content\n")
    result = render_template("trail.md", {}, tdir)
    assert result.endswith("\n")
