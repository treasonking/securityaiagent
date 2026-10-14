from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import ValidationError

from controller.providers import OpenAIModelProvider, ProviderDiagnosticCode


def _install_stub_agents(monkeypatch, *, output=None, error: Exception | None = None):
    captured = {}

    class StubAgent:
        def __init__(self, *, name, model, instructions, output_type):
            self.name = name
            self.model = model
            self.instructions = instructions
            self.output_type = output_type
            captured.update(
                name=name,
                model=model,
                instructions=instructions,
                output_type=output_type,
            )

    class StubRunner:
        @staticmethod
        async def run(agent, prompt, *, max_turns):
            captured.update(prompt=prompt, max_turns=max_turns)
            if error is not None:
                raise error
            final_output = agent.output_type.model_validate(output)
            usage = SimpleNamespace(
                requests=1,
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
            )
            return SimpleNamespace(
                final_output=final_output,
                context_wrapper=SimpleNamespace(usage=usage),
            )

    module = ModuleType("agents")
    module.Agent = StubAgent
    module.Runner = StubRunner
    module.set_tracing_disabled = lambda _disabled: None
    monkeypatch.setitem(sys.modules, "agents", module)
    return captured


def _configured_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-used")
    return OpenAIModelProvider(model_id="test-explicit-model", max_turns=3)


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


def test_live_provider_keeps_canonical_candidate_and_usage(monkeypatch):
    captured = _install_stub_agents(
        monkeypatch,
        output={
            "candidate_types": ["cross_account_document_access"],
            "rationale": "A bounded hypothesis for the published scenario.",
        },
    )
    result = asyncio.run(
        _configured_provider(monkeypatch).propose_candidates(
            scenario_id="access-control", target_id="lab-web"
        )
    )

    assert [item.finding_type for item in result.candidates] == [
        "cross_account_document_access"
    ]
    assert result.candidates[0].source == "openai_provider"
    assert result.diagnostics == ()
    assert result.usage.model_dump() == {
        "calls": 1,
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }
    assert "normal user-b control" in captured["instructions"]
    assert "user-a can access that same user-b-owned private document" in captured["instructions"]
    assert "exactly cross_account_document_access" in captured["instructions"]
    assert "otherwise return an empty candidate_types list" in captured["instructions"]
    assert "verifier, not you, decides the final verdict" in captured["instructions"]


def test_live_provider_preserves_intentional_empty_candidates(monkeypatch):
    _install_stub_agents(
        monkeypatch,
        output={"candidate_types": [], "rationale": "No bounded hypothesis proposed."},
    )
    result = asyncio.run(
        _configured_provider(monkeypatch).propose_candidates(
            scenario_id="access-control", target_id="lab-web"
        )
    )

    assert result.candidates == []
    assert result.diagnostics == (ProviderDiagnosticCode.EMPTY_CANDIDATES,)
    assert result.usage.calls == 1


def test_live_provider_deduplicates_canonical_candidate(monkeypatch):
    _install_stub_agents(
        monkeypatch,
        output={
            "candidate_types": [
                "cross_account_document_access",
                "cross_account_document_access",
            ],
            "rationale": "One bounded hypothesis repeated by the model.",
        },
    )
    result = asyncio.run(
        _configured_provider(monkeypatch).propose_candidates(
            scenario_id="access-control", target_id="lab-web"
        )
    )

    assert len(result.candidates) == 1


def test_live_provider_rejects_unregistered_scope_before_runner(monkeypatch):
    captured = _install_stub_agents(
        monkeypatch,
        output={"candidate_types": [], "rationale": "Not reached."},
    )
    with pytest.raises(ValueError, match="limited to access-control on lab-web"):
        asyncio.run(
            _configured_provider(monkeypatch).propose_candidates(
                scenario_id="access-control", target_id="unregistered-target"
            )
        )

    assert "prompt" not in captured


def test_live_provider_preserves_candidate_count_limit(monkeypatch):
    _install_stub_agents(
        monkeypatch,
        output={
            "candidate_types": ["cross_account_document_access"] * 5,
            "rationale": "Too many entries.",
        },
    )
    with pytest.raises(ValidationError):
        asyncio.run(
            _configured_provider(monkeypatch).propose_candidates(
                scenario_id="access-control", target_id="lab-web"
            )
        )


def test_live_provider_rejects_noncanonical_candidate_in_output_schema(monkeypatch):
    _install_stub_agents(
        monkeypatch,
        output={"candidate_types": ["idor"], "rationale": "Wrong vocabulary."},
    )
    with pytest.raises(ValidationError):
        asyncio.run(
            _configured_provider(monkeypatch).propose_candidates(
                scenario_id="access-control", target_id="lab-web"
            )
        )


def test_live_provider_does_not_convert_api_failure_to_empty_or_mock(monkeypatch):
    _install_stub_agents(monkeypatch, error=ConnectionError("synthetic API failure"))
    with pytest.raises(ConnectionError, match="synthetic API failure"):
        asyncio.run(
            _configured_provider(monkeypatch).propose_candidates(
                scenario_id="access-control", target_id="lab-web"
            )
        )
