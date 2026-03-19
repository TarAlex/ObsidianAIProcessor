"""Unit tests for agent/llm/provider_factory.py.

All concrete provider classes are replaced with lightweight stubs via
unittest.mock.patch.  No real HTTP calls are made.
"""
from __future__ import annotations

import logging
import sys
from unittest.mock import patch

import anyio
import pytest

from agent.core.config import AgentConfig, LLMConfig, ProviderConfig, VaultConfig
from agent.llm.base import AbstractLLMProvider, LLMProviderError


# ---------------------------------------------------------------------------
# Stub provider shared across all tests
# ---------------------------------------------------------------------------

class _StubProvider(AbstractLLMProvider):
    def __init__(self, name: str = "stub", model: str = "m", **kwargs):
        self._name = name
        self._model_id = model
        self.init_kwargs = kwargs  # capture for inspection

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def model_name(self) -> str:
        return self._model_id

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        return "ok"


class _FailingStubProvider(_StubProvider):
    """Stub that always raises LLMProviderError on chat()."""

    async def chat(self, messages, temperature=0.0, max_tokens=2000) -> str:
        raise LLMProviderError(
            "stub failure",
            provider=self.provider_name,
            model=self.model_name,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    default_provider: str = "ollama",
    fallback_chain: list[str] | None = None,
    providers: dict | None = None,
) -> AgentConfig:
    """Minimal AgentConfig for factory tests."""
    return AgentConfig(
        vault=VaultConfig(root="D:/ObsidianAIPoweredFlow"),  # path exists
        llm=LLMConfig(
            default_provider=default_provider,
            fallback_chain=fallback_chain if fallback_chain is not None else [default_provider],
            providers=providers or {},
        ),
    )


def _stub_registry() -> dict:
    """Registry where every key maps to a unique _StubProvider subclass."""
    stubs = {}
    for name in ("ollama", "lmstudio", "openai", "anthropic"):
        # Use default argument to capture the loop variable value immediately
        def _make_cls(captured_name: str) -> type:
            class _Named(_StubProvider):
                def __init__(self, **kwargs):
                    super().__init__(name=captured_name, **kwargs)
            _Named.__name__ = f"_Stub_{captured_name}"
            return _Named

        stubs[name] = _make_cls(name)
    return stubs


STUB_REGISTRY = _stub_registry()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_registry(monkeypatch):
    """Replace _REGISTRY in provider_factory with STUB_REGISTRY for all tests."""
    import agent.llm.provider_factory as pf
    monkeypatch.setattr(pf, "_REGISTRY", dict(STUB_REGISTRY))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetBasic:
    def test_get_returns_provider(self):
        cfg = _make_config(default_provider="ollama", fallback_chain=[])
        from agent.llm.provider_factory import ProviderFactory
        result = ProviderFactory.get(cfg)
        assert isinstance(result, AbstractLLMProvider)

    def test_get_no_fallbacks_returns_plain_provider(self):
        """Empty fallback_chain → no _FallbackProvider wrapper."""
        from agent.llm.provider_factory import ProviderFactory, _FallbackProvider
        cfg = _make_config(default_provider="ollama", fallback_chain=[])
        result = ProviderFactory.get(cfg)
        assert not isinstance(result, _FallbackProvider)

    def test_get_deduplicated_fallback_returns_plain_provider(self):
        """fallback_chain containing only the primary → no _FallbackProvider."""
        from agent.llm.provider_factory import ProviderFactory, _FallbackProvider
        cfg = _make_config(default_provider="ollama", fallback_chain=["ollama"])
        result = ProviderFactory.get(cfg)
        assert not isinstance(result, _FallbackProvider)

    def test_get_with_fallbacks_returns_fallback_provider(self):
        from agent.llm.provider_factory import ProviderFactory, _FallbackProvider
        cfg = _make_config(
            default_provider="ollama",
            fallback_chain=["ollama", "lmstudio"],
        )
        result = ProviderFactory.get(cfg)
        assert isinstance(result, _FallbackProvider)

    def test_primary_deduplicated_from_fallbacks(self):
        """_FallbackProvider._fallbacks must NOT contain the primary provider."""
        from agent.llm.provider_factory import ProviderFactory, _FallbackProvider
        cfg = _make_config(
            default_provider="ollama",
            fallback_chain=["ollama", "lmstudio"],
        )
        result = ProviderFactory.get(cfg)
        assert isinstance(result, _FallbackProvider)
        # Only lmstudio should be in _fallbacks
        assert len(result._fallbacks) == 1
        assert result._fallbacks[0].provider_name == "lmstudio"


class TestErrors:
    def test_unknown_provider_raises_valueerror(self):
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(default_provider="unknown", fallback_chain=[])
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            ProviderFactory.get(cfg)

    def test_unknown_fallback_raises_valueerror(self):
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(
            default_provider="ollama",
            fallback_chain=["ollama", "unknown"],
        )
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            ProviderFactory.get(cfg)


class TestConfigWiring:
    def test_base_url_from_config_passed(self):
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(
            default_provider="ollama",
            fallback_chain=[],
            providers={"ollama": ProviderConfig(base_url="http://custom:11434")},
        )
        result = ProviderFactory.get(cfg)
        assert result.init_kwargs.get("base_url") == "http://custom:11434"

    def test_default_model_from_config_passed(self):
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(
            default_provider="ollama",
            fallback_chain=[],
            providers={"ollama": ProviderConfig(default_model="llama3.1:8b")},
        )
        result = ProviderFactory.get(cfg)
        assert result.model_name == "llama3.1:8b"

    def test_api_key_resolved_from_env(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "sk-test")
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(
            default_provider="openai",
            fallback_chain=[],
            providers={"openai": ProviderConfig(api_key_env="TEST_KEY")},
        )
        result = ProviderFactory.get(cfg)
        assert result.init_kwargs.get("api_key") == "sk-test"

    def test_api_key_env_missing_passes_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(
            default_provider="openai",
            fallback_chain=[],
            providers={"openai": ProviderConfig(api_key_env="MISSING_KEY")},
        )
        result = ProviderFactory.get(cfg)
        assert result.init_kwargs.get("api_key") == ""

    def test_base_url_skipped_for_anthropic(self):
        """base_url must NOT be passed to AnthropicProvider."""
        from agent.llm.provider_factory import ProviderFactory
        cfg = _make_config(
            default_provider="anthropic",
            fallback_chain=[],
            providers={
                "anthropic": ProviderConfig(
                    base_url="http://proxy",
                    api_key_env="ANTHROPIC_API_KEY",
                )
            },
        )
        import os
        old = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        try:
            result = ProviderFactory.get(cfg)
            assert "base_url" not in result.init_kwargs
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old


class TestFallbackBehaviour:
    def test_fallback_chat_invoked_on_primary_failure(self):
        from agent.llm.provider_factory import _FallbackProvider

        async def run():
            primary = _FailingStubProvider(name="ollama")
            fallback = _StubProvider(name="lmstudio")

            # Override fallback to return a distinct value
            async def _fallback_chat(messages, temperature=0.0, max_tokens=2000):
                return "fallback_reply"

            fallback.chat = _fallback_chat

            fp = _FallbackProvider(primary, [fallback])
            return await fp.chat([{"role": "user", "content": "hi"}])

        result = anyio.run(run)
        assert result == "fallback_reply"

    def test_all_providers_fail_raises_last_error(self):
        from agent.llm.provider_factory import _FallbackProvider

        async def run():
            p1 = _FailingStubProvider(name="ollama")
            p2 = _FailingStubProvider(name="lmstudio")
            fp = _FallbackProvider(p1, [p2])
            with pytest.raises(LLMProviderError):
                await fp.chat([{"role": "user", "content": "hi"}])

        anyio.run(run)

    def test_warning_logged_on_primary_failure(self, caplog):
        from agent.llm.provider_factory import _FallbackProvider

        async def run():
            primary = _FailingStubProvider(name="ollama")
            fallback = _StubProvider(name="lmstudio")
            fp = _FallbackProvider(primary, [fallback])
            with caplog.at_level(logging.WARNING, logger="agent.llm.provider_factory"):
                await fp.chat([{"role": "user", "content": "hi"}])

        anyio.run(run)
        assert any("ollama" in r.message for r in caplog.records)

    def test_fallback_provider_name_reports_primary(self):
        from agent.llm.provider_factory import _FallbackProvider
        primary = _StubProvider(name="ollama")
        fp = _FallbackProvider(primary, [_StubProvider(name="lmstudio")])
        assert fp.provider_name == "ollama"

    def test_fallback_model_name_reports_primary(self):
        from agent.llm.provider_factory import _FallbackProvider
        primary = _StubProvider(name="ollama", model="llama3.2")
        fp = _FallbackProvider(primary, [_StubProvider(name="lmstudio")])
        assert fp.model_name == "llama3.2"


class TestAlias:
    def test_get_provider_alias_same_result(self):
        from agent.llm.provider_factory import ProviderFactory, get_provider
        cfg = _make_config(default_provider="ollama", fallback_chain=[])
        r1 = ProviderFactory.get(cfg)
        r2 = get_provider(cfg)
        # Both should be the same type and provider_name
        assert type(r1) is type(r2)
        assert r1.provider_name == r2.provider_name


class TestNoVaultImport:
    def test_no_vault_import(self):
        """Importing provider_factory must not transitively import agent.vault."""
        # Ensure the module is imported
        import agent.llm.provider_factory  # noqa: F401
        for mod_name in sys.modules:
            assert not mod_name.startswith("agent.vault"), (
                f"agent.vault was transitively imported by provider_factory: {mod_name}"
            )
