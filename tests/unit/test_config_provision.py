"""Tests for agent.cli.config_provision."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent.cli.config_provision import (
    DEFAULT_OLLAMA_URL,
    ProvisionSpec,
    apply_spec_to_data,
    minimal_config_template,
    provision_write,
    task_routing_for,
    upsert_env_file,
    validate_provisioned_dict,
)
from agent.core.config import ConfigError


def test_minimal_template_validates(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    data = minimal_config_template(str(vault.resolve()))
    data["vault"]["root"] = str(vault.resolve())
    validate_provisioned_dict(data)


def test_task_routing_for() -> None:
    tr = task_routing_for("openai", "gpt-4o-mini", "nomic-embed-text")
    assert tr["classification"] == "openai/gpt-4o-mini"
    assert tr["embeddings"] == "ollama/nomic-embed-text"


def test_provision_write_ollama(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = vault / "_AI_META" / "agent-config.yaml"
    spec = ProvisionSpec(vault_root=vault, default_provider="ollama")
    r = provision_write(cfg, spec)
    assert r.config_path == cfg.resolve()
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "api_key" not in yaml.dump(raw)
    assert raw["vault"]["root"] == str(vault.resolve())
    assert raw["llm"]["default_provider"] == "ollama"


def test_provision_openai_no_secret_in_yaml(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = vault / "_AI_META" / "agent-config.yaml"
    spec = ProvisionSpec(
        vault_root=vault,
        default_provider="openai",
        openai_model="gpt-4o-mini",
        fallback_chain=["openai"],
    )
    provision_write(cfg, spec, extra_env={"OPENAI_API_KEY": "sk-secret"})
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert raw["llm"]["providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"
    assert "sk-secret" not in cfg.read_text(encoding="utf-8")
    env_file = cfg.parent / ".env"
    assert "sk-secret" in env_file.read_text(encoding="utf-8")


def test_ollama_nondefault_url_writes_env(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = vault / "_AI_META" / "agent-config.yaml"
    spec = ProvisionSpec(
        vault_root=vault,
        default_provider="ollama",
        ollama_url="http://10.0.0.5:11434",
        fallback_chain=["ollama"],
    )
    provision_write(cfg, spec)
    env_text = (cfg.parent / ".env").read_text(encoding="utf-8")
    assert "OLLAMA_BASE_URL=http://10.0.0.5:11434" in env_text.replace('"', "")


def test_reject_literal_api_key_in_yaml_merge(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    base = minimal_config_template(str(vault.resolve()))
    base["llm"]["providers"]["openai"] = {
        "api_key": "nope",
        "default_model": "gpt-4o-mini",
    }
    spec = ProvisionSpec(vault_root=vault, default_provider="ollama")
    with pytest.raises(ConfigError, match="api_key"):
        data = apply_spec_to_data(base, spec)
        validate_provisioned_dict(data)


def test_upsert_env_file_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    upsert_env_file(p, {"A": "1"})
    upsert_env_file(p, {"B": "two words"})
    text = p.read_text(encoding="utf-8")
    assert "A=1" in text
    assert 'B="two words"' in text or "B=" in text
