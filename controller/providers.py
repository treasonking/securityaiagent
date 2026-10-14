from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from common.schemas import FindingCandidate, ModelUsage


class ProviderDiagnosticCode(StrEnum):
    EMPTY_CANDIDATES = "EMPTY_CANDIDATES"


@dataclass(frozen=True)
class ProviderResult:
    candidates: list[FindingCandidate]
    usage: ModelUsage
    diagnostics: tuple[ProviderDiagnosticCode, ...] = ()


class ModelProvider(Protocol):
    mode: str
    model_id: str | None

    async def propose_candidates(self, *, scenario_id: str, target_id: str) -> ProviderResult: ...


class MockModelProvider:
    mode = "mock"
    model_id = None

    async def propose_candidates(self, *, scenario_id: str, target_id: str) -> ProviderResult:
        if scenario_id != "access-control" or target_id != "lab-web":
            return ProviderResult(candidates=[], usage=ModelUsage())
        return ProviderResult(
            candidates=[
                FindingCandidate(
                    finding_type="cross_account_document_access",
                    rationale="Published scenario asks whether user-a can retrieve user-b's synthetic private document.",
                    source="mock_provider",
                )
            ],
            usage=ModelUsage(),
        )


class _AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_types: list[Literal["cross_account_document_access"]] = Field(max_length=4)
    rationale: str = Field(max_length=1200)


class OpenAIModelProvider:
    mode = "openai"

    def __init__(self, *, model_id: str | None = None, max_turns: int = 8) -> None:
        self.model_id = model_id or os.getenv("OPENAI_MODEL") or None
        self.max_turns = max_turns

    async def propose_candidates(self, *, scenario_id: str, target_id: str) -> ProviderResult:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for provider=openai")
        if not self.model_id:
            raise RuntimeError("OPENAI_MODEL must be explicitly configured for provider=openai")
        if scenario_id != "access-control" or target_id != "lab-web":
            raise ValueError("openai provider is limited to access-control on lab-web")
        from agents import Agent, Runner, set_tracing_disabled

        set_tracing_disabled(True)
        agent = Agent(
            name="SecurityLab candidate planner",
            model=self.model_id,
            instructions=(
                "This is the published synthetic access-control scenario only. "
                "It asks whether the normal user-b control can access user-b's own private document "
                "and whether user-a can access that same user-b-owned private document. "
                "A candidate is only an unverified hypothesis to test, never a verdict. "
                "The only allowed candidate name is exactly cross_account_document_access. "
                "Return that name only when it is a useful hypothesis for this scenario; otherwise "
                "return an empty candidate_types list. Do not add a candidate merely to avoid an empty list. "
                "You do not receive actual HTTP responses, target logs, target mode, expected answers, "
                "or verifier fixtures. "
                "Never invent URLs, tools, credentials, shell commands, targets, or confirmed findings. "
                "A verifier, not you, decides the final verdict."
            ),
            output_type=_AgentOutput,
        )
        result = await Runner.run(
            agent,
            f"scenario_id={scenario_id}; target_id={target_id}; propose bounded candidate types",
            max_turns=self.max_turns,
        )
        output = _AgentOutput.model_validate(result.final_output)
        candidates = [
            FindingCandidate(
                finding_type=item,
                rationale=output.rationale,
                source="openai_provider",
            )
            for item in dict.fromkeys(output.candidate_types)
        ]
        usage_obj = getattr(getattr(result, "context_wrapper", None), "usage", None)
        usage = ModelUsage(
            calls=int(getattr(usage_obj, "requests", 1) or 1),
            input_tokens=int(getattr(usage_obj, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage_obj, "output_tokens", 0) or 0),
            total_tokens=int(getattr(usage_obj, "total_tokens", 0) or 0),
        )
        diagnostics = (
            (ProviderDiagnosticCode.EMPTY_CANDIDATES,) if not candidates else ()
        )
        return ProviderResult(candidates=candidates, usage=usage, diagnostics=diagnostics)


def get_provider(mode: str, *, model_id: str | None = None, max_turns: int = 8) -> ModelProvider:
    if mode == "mock":
        return MockModelProvider()
    if mode == "openai":
        return OpenAIModelProvider(model_id=model_id, max_turns=max_turns)
    raise ValueError("provider must be mock or openai")
