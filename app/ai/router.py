"""Model routing and metered execution.

`LLMGateway` is the only way the engine calls a model. It:

* picks the model for a task (writer / utility / fallback) from configuration;
* checks the budget before spending;
* records actual token usage and cost into ``llm_runs`` and ``cost_ledger``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.ai.budget import BudgetManager
from app.ai.mock_provider import MockLLMProvider
from app.ai.pricing import estimate_cost
from app.ai.prompts import Prompt
from app.ai.provider import LLMProvider, LLMRequest, LLMResponse
from app.config import Market, Settings, get_settings
from app.db.enums import CostKind, LLMTask
from app.db.models import LLMRun
from app.errors import BudgetExceeded, LLMError
from app.logging_setup import get_logger

log = get_logger("ai.router")

#: Tasks that must use the high-quality writer model.
WRITER_TASKS = {LLMTask.ARTICLE_WRITE, LLMTask.OUTLINE}

#: Everything else runs on the cheap utility model (spec §12.1, §48).
UTILITY_TASKS = {
    LLMTask.TOPIC_EXPANSION,
    LLMTask.TOPIC_SCORING,
    LLMTask.DEDUPLICATION,
    LLMTask.CLASSIFICATION,
    LLMTask.CLAIM_EXTRACTION,
    LLMTask.FACT_RESEARCH,
    LLMTask.QUALITY_REVIEW,
    LLMTask.REWRITE,
}


class ModelRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def model_for(self, task: LLMTask, *, escalate: bool = False) -> str:
        if escalate:
            return self.settings.openai_fallback_model
        if task in WRITER_TASKS:
            return self.settings.openai_writer_model
        if task == LLMTask.QUALITY_REVIEW:
            return self.settings.review_model
        return self.settings.openai_utility_model


@dataclass(slots=True)
class GatewayResult:
    response: LLMResponse
    cost_usd: float
    run_id: int | None


class LLMGateway:
    def __init__(
        self,
        session: Session,
        provider: LLMProvider | None = None,
        *,
        settings: Settings | None = None,
        budget: BudgetManager | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider or build_llm_provider(self.settings)
        self.router = ModelRouter(self.settings)
        self.budget = budget or BudgetManager(session, self.settings)

    def run(
        self,
        *,
        task: LLMTask,
        prompt: Prompt,
        payload: str,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "response",
        market: Market | None = None,
        article_id: int | None = None,
        topic_id: int | None = None,
        job_id: str | None = None,
        escalate: bool = False,
        enable_web_search: bool = False,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        enforce_budget: bool = True,
    ) -> GatewayResult:
        model = self.router.model_for(task, escalate=escalate)

        if enforce_budget and self.budget.hard_cap_reached():
            raise BudgetExceeded(
                "daily AI budget exhausted",
                remaining_usd=0.0,
                projected_usd=0.0,
            )

        request = LLMRequest(
            model=model,
            instructions=prompt.body,
            input=payload,
            json_schema=json_schema,
            schema_name=schema_name,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            enable_web_search=enable_web_search,
            metadata={"task": str(task), "prompt": f"{prompt.name}:{prompt.version}"},
        )

        started = time.monotonic()
        run = LLMRun(
            job_id=job_id,
            article_id=article_id,
            topic_id=topic_id,
            market=market,
            task=str(task),
            model=model,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
        )
        self.session.add(run)
        self.session.flush()

        try:
            response = self.provider.complete(request)
        except LLMError as exc:
            run.status = "error"
            run.error = str(exc)
            run.duration_ms = int((time.monotonic() - started) * 1000)
            self.session.flush()
            raise

        usage = response.usage
        cost = estimate_cost(
            model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            web_search_calls=usage.web_search_calls,
        )

        run.input_tokens = usage.input_tokens
        run.cached_input_tokens = usage.cached_input_tokens
        run.output_tokens = usage.output_tokens
        run.reasoning_tokens = usage.reasoning_tokens
        run.tool_calls = usage.tool_calls
        run.web_search_calls = usage.web_search_calls
        run.cost_usd = cost
        run.duration_ms = response.duration_ms or int((time.monotonic() - started) * 1000)
        run.status = "ok"
        self.session.flush()

        self.budget.record(
            amount_usd=cost,
            market=market,
            article_id=article_id,
            llm_run_id=run.id,
            kind=CostKind.WEB_SEARCH if usage.web_search_calls else CostKind.LLM,
            task=str(task),
            model=model,
        )

        log.info(
            "llm.run",
            task=str(task),
            model=model,
            market=market,
            article_id=article_id,
            cost_usd=round(cost, 6),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            duration_ms=run.duration_ms,
            status="ok",
        )
        return GatewayResult(response=response, cost_usd=cost, run_id=run.id)


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "mock" or not settings.openai_api_key:
        if settings.llm_provider != "mock":
            log.warning("ai.no_api_key_falling_back_to_mock")
        return MockLLMProvider()
    from app.ai.openai_provider import OpenAIProvider

    return OpenAIProvider(settings)


__all__ = [
    "UTILITY_TASKS",
    "WRITER_TASKS",
    "GatewayResult",
    "LLMGateway",
    "ModelRouter",
    "build_llm_provider",
]
