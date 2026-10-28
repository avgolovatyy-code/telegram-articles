"""OpenAI Chief Editor daily planner (spec §6.4a)."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.prompts import chief_editor_prompt
from app.ai.router import LLMGateway
from app.config import MARKETS, Market, Settings, get_settings
from app.db.enums import LLMTask
from app.db.models import EditorialRun
from app.db.types import utcnow
from app.editorial.brief import build_daily_brief
from app.editorial.planner import apply_decision_set, last_valid_run
from app.editorial.schemas import EditorialDecisionSet, editorial_decision_json_schema
from app.errors import LLMError
from app.logging_setup import get_logger

log = get_logger("editorial.chief_editor")


@dataclass(slots=True)
class ChiefEditorReport:
    ok: bool = True
    details: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ChiefEditorService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        gateway: LLMGateway | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.gateway = gateway or LLMGateway(session, settings=self.settings)

    def run(
        self,
        *,
        markets: tuple[Market, ...] = MARKETS,
        run_date: dt.date | None = None,
    ) -> ChiefEditorReport:
        if not self.settings.editorial_v2_enabled:
            return ChiefEditorReport(
                ok=True,
                details={"skipped": "EDITORIAL_V2_ENABLED=false"},
            )
        if not self.settings.openai_chief_editor_daily:
            return ChiefEditorReport(
                ok=True,
                details={"skipped": "OPENAI_CHIEF_EDITOR_DAILY=false"},
            )

        report = ChiefEditorReport()
        run_date = run_date or utcnow().astimezone(self.settings.publish_tz).date()
        dry_run = self.settings.editorial_v2_dry_run

        for market in markets:
            try:
                run = self._run_market(market, run_date=run_date, dry_run=dry_run)
                report.details[f"{market}_run_id"] = run.run_id
                report.details[f"{market}_status"] = run.status
                report.details[f"{market}_thesis"] = (run.editorial_thesis or "")[:120]
                report.details[f"{market}_slots"] = (run.diff or {}).get("applied_slots", 0)
            except Exception as exc:
                report.ok = False
                msg = f"{market}: {exc}"
                if isinstance(exc, LLMError) and exc.payload:
                    snippet = str(exc.payload)[:240].replace("\n", " ")
                    msg = f"{msg} — {snippet}"
                report.errors.append(msg)
                log.error("chief_editor.failed", market=market, error=str(exc))
                self._record_failure(market, run_date, msg)
                previous = last_valid_run(self.session, market)
                if previous is not None:
                    report.details[f"{market}_kept_last_plan"] = previous.run_id
        return report

    def _run_market(
        self, market: Market, *, run_date: dt.date, dry_run: bool
    ) -> EditorialRun:
        brief = build_daily_brief(self.session, market, self.settings, run_date=run_date)
        prompt = chief_editor_prompt(market)
        payload = json.dumps(brief, ensure_ascii=False)
        schema = editorial_decision_json_schema()

        result = self.gateway.run(
            task=LLMTask.CHIEF_EDITOR,
            prompt=prompt,
            payload=payload,
            json_schema=schema,
            schema_name="editorial_decision_set",
            market=market,
            enforce_budget=True,
            max_output_tokens=4000,
        )
        parsed = result.response.parsed
        if not isinstance(parsed, dict):
            raise LLMError("Chief Editor returned no structured payload")
        decision_set = EditorialDecisionSet.model_validate(parsed)
        if decision_set.market != market:
            decision_set = decision_set.model_copy(update={"market": market})
        if decision_set.run_date != run_date:
            decision_set = decision_set.model_copy(update={"run_date": run_date})

        return apply_decision_set(
            self.session,
            market=market,
            run_date=run_date,
            decision_set=decision_set,
            brief=brief,
            llm_run_id=result.run_id,
            settings=self.settings,
            dry_run=dry_run,
        )

    def _record_failure(self, market: Market, run_date: dt.date, error: str) -> None:
        from uuid import uuid4

        row = EditorialRun(
            run_id=str(uuid4()),
            run_date=run_date,
            market=market,
            status="failed",
            dry_run=self.settings.editorial_v2_dry_run,
            brief={},
            decisions={},
            diff={},
            error=error[:2000],
        )
        self.session.add(row)
        self.session.flush()


__all__ = ["ChiefEditorReport", "ChiefEditorService"]
