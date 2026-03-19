"""Unit tests for agent/adapters/base.py — pure interface, no I/O."""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType


# ---------------------------------------------------------------------------
# AdapterError
# ---------------------------------------------------------------------------

class TestAdapterError:
    def test_is_exception_subclass(self):
        assert issubclass(AdapterError, Exception)

    def test_message_and_path_attributes(self):
        p = Path("/x")
        err = AdapterError("msg", p)
        assert err.args[0] == "msg"
        assert err.path == p


# ---------------------------------------------------------------------------
# BaseAdapter instantiation
# ---------------------------------------------------------------------------

class TestBaseAdapterInstantiation:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseAdapter()  # type: ignore[abstract]

    def test_concrete_subclass_can_be_instantiated(self):
        class ConcreteAdapter(BaseAdapter):
            async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
                ...  # pragma: no cover

        adapter = ConcreteAdapter()
        assert isinstance(adapter, BaseAdapter)


# ---------------------------------------------------------------------------
# _generate_raw_id
# ---------------------------------------------------------------------------

RAW_ID_PATTERN = re.compile(r"^SRC-\d{8}-\d{6}$")


class TestGenerateRawId:
    def test_matches_expected_format(self):
        raw_id = BaseAdapter._generate_raw_id()
        assert RAW_ID_PATTERN.match(raw_id), f"Got: {raw_id!r}"

    def test_two_calls_both_match_format(self):
        id1 = BaseAdapter._generate_raw_id()
        id2 = BaseAdapter._generate_raw_id()
        assert RAW_ID_PATTERN.match(id1), f"id1: {id1!r}"
        assert RAW_ID_PATTERN.match(id2), f"id2: {id2!r}"


# ---------------------------------------------------------------------------
# Abstract method contract
# ---------------------------------------------------------------------------

class TestAbstractContract:
    def test_extract_is_abstract(self):
        assert inspect.isabstract(BaseAdapter)

    def test_extract_listed_in_abstractmethods(self):
        assert "extract" in BaseAdapter.__abstractmethods__


# ---------------------------------------------------------------------------
# Import cleanliness — no optional heavy deps at module level
# ---------------------------------------------------------------------------

class TestImportCleanness:
    def test_module_imports_without_optional_deps(self):
        """Re-import should succeed; heavy deps are not required at module level."""
        import importlib
        import sys

        # Remove cached module to force re-import
        mod_name = "agent.adapters.base"
        sys.modules.pop(mod_name, None)
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, "BaseAdapter")
        assert hasattr(mod, "AdapterError")
