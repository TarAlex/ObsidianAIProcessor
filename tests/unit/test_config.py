"""Tests for agent/core/config.py — all 13 cases from the spec."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from agent.core.config import AgentConfig, ConfigError, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def _minimal_data(vault_root: str) -> dict:
    return {"vault": {"root": vault_root}}


def _full_data(vault_root: str) -> dict:
    return {
        "vault": {
            "root": vault_root,
            "review_threshold": 0.75,
            "merge_threshold": 0.85,
            "related_threshold": 0.55,
            "max_verbatim_blocks_per_note": 5,
            "verbatim_high_risk_age": 180,
        },
        "llm": {
            "default_provider": "ollama",
            "review_threshold": 0.70,
            "fallback_chain": ["ollama", "openai"],
            "providers": {
                "ollama": {
                    "base_url": "http://127.0.0.1:11434",
                    "default_model": "llama3.1:8b",
                    "embedding_model": "nomic-embed-text",
                },
                "openai": {
                    "base_url": None,
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                },
            },
            "task_routing": {
                "classification": "ollama/llama3.1:8b",
                "summarization": "ollama/llama3.1:8b",
                "verbatim_extraction": "ollama/llama3.1:8b",
                "atom_extraction": "ollama/llama3.1:8b",
                "embeddings": "ollama/nomic-embed-text",
            },
        },
        "whisper": {"model": "large", "language": "en"},
        "scheduler": {
            "poll_interval_minutes": 30,
            "outdated_review_day": "friday",
            "outdated_review_hour": 10,
        },
        "sync": {
            "check_lock_before_write": False,
            "lock_wait_timeout_s": 30,
            "sync_poll_interval_s": 10,
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault_dir(tmp_path: Path) -> Path:
    """A minimal fake vault root directory."""
    vr = tmp_path / "vault"
    vr.mkdir()
    return vr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadValidConfig:
    def test_load_valid_config(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "agent-config.yaml", _full_data(str(vault_dir)))
        cfg = load_config(cfg_path)

        assert isinstance(cfg, AgentConfig)
        assert cfg.vault.root == str(vault_dir)
        assert cfg.vault.max_verbatim_blocks_per_note == 5
        assert cfg.vault.verbatim_high_risk_age == 180
        assert cfg.vault.review_threshold == 0.75
        assert cfg.llm.default_provider == "ollama"
        assert cfg.llm.fallback_chain == ["ollama", "openai"]
        assert cfg.llm.providers["openai"].api_key_env == "OPENAI_API_KEY"
        assert cfg.llm.task_routing.verbatim_extraction == "ollama/llama3.1:8b"
        assert cfg.whisper.model == "large"
        assert cfg.whisper.language == "en"
        assert cfg.scheduler.poll_interval_minutes == 30
        assert cfg.sync.check_lock_before_write is False


class TestDefaultsApplied:
    def test_defaults_applied(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)

        assert cfg.vault.max_verbatim_blocks_per_note == 10
        assert cfg.vault.verbatim_high_risk_age == 365
        assert cfg.vault.review_threshold == 0.70
        assert cfg.vault.merge_threshold == 0.80
        assert cfg.vault.related_threshold == 0.60
        assert cfg.llm.default_provider == "ollama"
        assert cfg.llm.fallback_chain == ["ollama"]
        assert cfg.llm.providers == {}
        assert cfg.whisper.model == "medium"
        assert cfg.whisper.language is None
        assert cfg.scheduler.poll_interval_minutes == 15
        assert cfg.scheduler.outdated_review_day == "monday"
        assert cfg.scheduler.outdated_review_hour == 9
        assert cfg.sync.check_lock_before_write is True
        assert cfg.sync.lock_wait_timeout_s == 60
        assert cfg.sync.sync_poll_interval_s == 5


class TestMissingVaultRootField:
    def test_missing_vault_root_field(self, tmp_path: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", {"vault": {}})
        with pytest.raises(ConfigError):
            load_config(cfg_path)

    def test_missing_vault_section_entirely(self, tmp_path: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", {"llm": {}})
        with pytest.raises(ConfigError):
            load_config(cfg_path)


class TestVaultRootNotOnDisk:
    def test_vault_root_not_on_disk(self, tmp_path: Path) -> None:
        fake_root = str(tmp_path / "nonexistent_vault")
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(fake_root))
        with pytest.raises(ConfigError, match="vault.root does not exist"):
            load_config(cfg_path)


class TestMalformedYaml:
    def test_malformed_yaml(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("vault:\n  root: [\nbad yaml {{{", encoding="utf-8")
        with pytest.raises(ConfigError, match="Malformed YAML"):
            load_config(cfg_path)


class TestApiKeyLiteralRejected:
    def test_api_key_literal_rejected(self, tmp_path: Path, vault_dir: Path) -> None:
        data = _minimal_data(str(vault_dir))
        data["llm"] = {
            "providers": {
                "openai": {
                    "api_key": "sk-real-secret",
                    "default_model": "gpt-4o-mini",
                }
            }
        }
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", data)
        with pytest.raises(ConfigError, match="api_key_env"):
            load_config(cfg_path)


class TestApiKeyEnvNameStored:
    def test_api_key_env_name_stored(self, tmp_path: Path, vault_dir: Path) -> None:
        data = _full_data(str(vault_dir))
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", data)
        cfg = load_config(cfg_path)

        openai = cfg.llm.providers["openai"]
        # Stored as the NAME string only
        assert openai.api_key_env == "OPENAI_API_KEY"
        # The model does not store a resolved key value
        assert not hasattr(openai, "api_key")


class TestDotenvOverlay:
    def test_dotenv_overlay(self, tmp_path: Path, vault_dir: Path) -> None:
        # Write .env next to the YAML file
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("OBSIDIAN_TEST_KEY=test-value-123\n", encoding="utf-8")

        # Ensure the env var is NOT set before the call
        os.environ.pop("OBSIDIAN_TEST_KEY", None)

        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        load_config(cfg_path)

        # After load_config the env var should be readable
        assert os.environ.get("OBSIDIAN_TEST_KEY") == "test-value-123"

        # Cleanup
        os.environ.pop("OBSIDIAN_TEST_KEY", None)

    def test_dotenv_override_false(self, tmp_path: Path, vault_dir: Path) -> None:
        """Existing env vars must NOT be overwritten (override=False)."""
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("OBSIDIAN_OVERRIDE_TEST=from-dotenv\n", encoding="utf-8")

        os.environ["OBSIDIAN_OVERRIDE_TEST"] = "from-process"

        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        load_config(cfg_path)

        assert os.environ["OBSIDIAN_OVERRIDE_TEST"] == "from-process"

        os.environ.pop("OBSIDIAN_OVERRIDE_TEST", None)


class TestTagTaxonomySummary:
    def test_tag_taxonomy_summary_present(self, tmp_path: Path, vault_dir: Path) -> None:
        ai_meta = vault_dir / "_AI_META"
        ai_meta.mkdir()
        taxonomy_file = ai_meta / "tag-taxonomy.md"
        taxonomy_file.write_text("# Tags\n" + "x" * 3000, encoding="utf-8")

        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)

        summary = cfg.tag_taxonomy_summary
        assert len(summary) <= 2000
        assert summary.startswith("# Tags")

    def test_tag_taxonomy_summary_missing(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)

        assert cfg.tag_taxonomy_summary == ""


class TestDomainsProperty:
    def test_domains_property(self, tmp_path: Path, vault_dir: Path) -> None:
        knowledge = vault_dir / "02_KNOWLEDGE"
        knowledge.mkdir()
        (knowledge / "Science").mkdir()
        (knowledge / "History").mkdir()
        (knowledge / "not_a_dir.md").write_text("", encoding="utf-8")

        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)

        assert cfg.domains == ["History", "Science"]

    def test_domains_empty_if_no_knowledge_dir(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)

        assert cfg.domains == []


class TestLoadConfigAcceptsStrAndPath:
    def test_accepts_str(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(str(cfg_path))
        assert isinstance(cfg, AgentConfig)

    def test_accepts_path(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)  # Path object
        assert isinstance(cfg, AgentConfig)


class TestVaultRootProperty:
    def test_vault_root_returns_path(self, tmp_path: Path, vault_dir: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "cfg.yaml", _minimal_data(str(vault_dir)))
        cfg = load_config(cfg_path)
        assert isinstance(cfg.vault_root, Path)
        assert cfg.vault_root == vault_dir
