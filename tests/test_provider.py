from __future__ import annotations

import asyncio

import pytest

from controller.providers import OpenAIModelProvider


def test_live_provider_requires_key_and_explicit_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    provider = OpenAIModelProvider()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        asyncio.run(provider.propose_candidates(scenario_id="access-control", target_id="lab-web"))


def test_live_provider_does_not_invent_default_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-used")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    provider = OpenAIModelProvider()
    with pytest.raises(RuntimeError, match="OPENAI_MODEL"):
        asyncio.run(provider.propose_candidates(scenario_id="access-control", target_id="lab-web"))
