"""agent/vault/templates.py — Jinja2 template rendering for vault index and note files.

Public API:
    render_template(name, ctx, template_dir) → str
    get_template_path(vault_root) → Path
"""
from __future__ import annotations

from pathlib import Path

import jinja2

# In-process cache: keyed by resolved template_dir string.
_ENV_CACHE: dict[str, jinja2.Environment] = {}


def _get_env(template_dir: Path) -> jinja2.Environment:
    key = str(template_dir.resolve())
    if key not in _ENV_CACHE:
        _ENV_CACHE[key] = jinja2.Environment(
            loader=jinja2.FileSystemLoader(key),
            autoescape=False,
            keep_trailing_newline=True,
        )
    return _ENV_CACHE[key]


def render_template(name: str, ctx: dict, template_dir: Path) -> str:
    """Render a named Jinja2 template with the given context dict.

    Args:
        name:         Filename relative to template_dir (e.g. "domain_index.md").
        ctx:          Jinja2 context variables. None values for optional vars render
                      as empty string (Undefined default behaviour).
        template_dir: Absolute path to the templates directory.

    Returns:
        Rendered template string.

    Raises:
        FileNotFoundError: If template_dir does not exist, or if the template name
                           is not found inside template_dir.
        jinja2.TemplateSyntaxError: Propagates unchanged so callers can diagnose
                                    malformed templates.
    """
    if not template_dir.exists():
        raise FileNotFoundError(
            f"Template directory does not exist: {template_dir}"
        )
    env = _get_env(template_dir)
    try:
        template = env.get_template(name)
    except jinja2.TemplateNotFound:
        raise FileNotFoundError(f"Template not found: {template_dir / name}")
    return template.render(ctx)


def get_template_path(vault_root: Path) -> Path:
    """Return the templates directory path derived from vault_root.

    Equivalent to: vault_root / "_AI_META" / "templates"
    Callers that have an AgentConfig use get_template_path(config.vault_root).
    """
    return vault_root / "_AI_META" / "templates"
