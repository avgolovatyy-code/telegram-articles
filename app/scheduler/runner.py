"""APScheduler wiring.

Deliberately simple: one in-process scheduler, jobs that own their own transaction, no
Celery/Kafka/Kubernetes for a workload of a few dozen articles a day.
"""

from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Settings, get_settings
from app.db.base import session_scope
from app.logging_setup import get_logger
from app.scheduler import jobs

log = get_logger("scheduler")


def _wrap(func: Callable[..., jobs.JobReport], name: str, settings: Settings) -> Callable[[], None]:
    def runner() -> None:
        try:
            with session_scope() as session:
                report = func(session, settings=settings)
            log.info("scheduler.job_done", job=name, ok=report.ok, details=report.details)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log.error("scheduler.job_failed", job=name, error=detail)
            _alert(name, detail, settings)

    runner.__name__ = f"job_{name}"
    return runner


def _alert(job: str, detail: str, settings: Settings) -> None:
    """Tell Slack that a scheduled job failed; never raise from here."""
    try:
        from app.slack.notifications import SlackNotifier

        with session_scope() as session:
            SlackNotifier(session, settings).alert(f"Джоба {job} упала", detail)
    except Exception:
        log.warning("scheduler.alert_failed", job=job)


class SchedulerRunner:
    """Owns the schedule shared by the API process and the standalone worker."""

    def __init__(self, settings: Settings | None = None, *, blocking: bool = False) -> None:
        self.settings = settings or get_settings()
        self.scheduler = (
            BlockingScheduler(timezone=self.settings.timezone)
            if blocking
            else BackgroundScheduler(timezone=self.settings.timezone)
        )
        self._configure()

    def _configure(self) -> None:
        settings = self.settings
        add = self.scheduler.add_job

        add(
            _wrap(jobs.sync_catalog, "sync_catalog", settings),
            CronTrigger(hour=2, minute=0),
            id="sync_catalog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        add(
            _wrap(jobs.discover_topics, "discover_topics", settings),
            CronTrigger(hour=3, minute=0),
            id="discover_topics",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        add(
            _wrap(jobs.generate_daily_articles, "generate_articles", settings),
            CronTrigger(hour="4,10,16", minute=0),
            id="generate_articles",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        add(
            _wrap(jobs.schedule_publications, "schedule_publications", settings),
            CronTrigger(hour="5,11,17", minute=30),
            id="schedule_publications",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        add(
            _wrap(jobs.process_publication_queue, "publication_queue", settings),
            IntervalTrigger(minutes=5),
            id="publication_queue",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        add(
            _wrap(jobs.cleanup_expired, "cleanup", settings),
            IntervalTrigger(minutes=30),
            id="cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        add(
            _wrap(jobs.send_daily_digest, "slack_digest", settings),
            CronTrigger(hour=settings.slack_digest_hour, minute=0),
            id="slack_digest",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            log.warning("scheduler.shutdown_failed")

    def jobs_summary(self) -> list[dict[str, str]]:
        return [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else "paused",
            }
            for job in self.scheduler.get_jobs()
        ]


__all__ = ["SchedulerRunner"]
