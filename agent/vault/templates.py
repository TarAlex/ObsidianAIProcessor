"""agent/vault/templates.py — Jinja2 template rendering for vault index files.

Stub implementation — full Jinja2 rendering is implemented in the templates-py spec.
Tests patch this module's render_template to avoid requiring Jinja2 before that spec ships.
"""
from __future__ import annotations


def render_template(template_name: str, context: dict) -> str:
    """Render a named template with the given context dict.

    Raises NotImplementedError until the templates-py spec is implemented.
    """
    raise NotImplementedError(
        f"render_template('{template_name}') — templates.py not yet fully implemented"
    )
