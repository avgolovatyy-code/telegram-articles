"""Command line interface: ``wgt <command>``."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import pathlib
from typing import Annotated

import typer

from app.config import MARKETS, Market, get_settings
from app.db.base import session_scope
from app.logging_setup import configure_logging, get_logger
from app.scheduler import jobs
from app.scheduler.runner import SchedulerRunner

app = typer.Typer(help="WeGoTrip Telegram Content Engine", no_args_is_help=True)
log = get_logger("cli")


def _bootstrap() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


def _markets(market: str | None) -> tuple[Market, ...]:
    if not market:
        return MARKETS
    if market not in MARKETS:
        raise typer.BadParameter(f"unknown market {market}; expected one of {MARKETS}")
    return (market,)  # type: ignore[return-value]


def _print(report: jobs.JobReport) -> None:
    typer.echo(
        json.dumps({"job": report.name, "ok": report.ok, **report.details}, indent=2, default=str)
    )
    for error in report.errors:
        typer.secho(f"  error: {error}", fg=typer.colors.RED)


@app.command()
def seed() -> None:
    """Create market rows, keyword clusters and prompt versions."""
    _bootstrap()
    with session_scope() as session:
        _print(jobs.seed_reference_data(session))


@app.command("sync-catalog")
def sync_catalog(
    market: Annotated[str | None, typer.Option(help="en or ru; default both")] = None,
    max_products: Annotated[int, typer.Option(help="upper bound on products per market")] = 400,
    detail_products: Annotated[int, typer.Option(help="how many products to fetch in detail")] = 60,
    cities_for_attractions: Annotated[int, typer.Option()] = 25,
) -> None:
    """Synchronise the WeGoTrip catalogue for one or both markets."""
    _bootstrap()
    from app.catalog.sync import SyncOptions

    options = SyncOptions(
        cities_for_attractions=cities_for_attractions,
        max_products=max_products,
        detail_products=detail_products,
    )
    with session_scope() as session:
        _print(jobs.sync_catalog(session, markets=_markets(market), options=options))


@app.command("discover-topics")
def discover_topics(
    market: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int | None, typer.Option()] = None,
) -> None:
    """Build topic candidates from the catalogue and the intent clusters."""
    _bootstrap()
    with session_scope() as session:
        _print(jobs.discover_topics(session, markets=_markets(market), limit=limit))


@app.command()
def generate(
    market: Annotated[str | None, typer.Option()] = None,
    max_articles: Annotated[int | None, typer.Option(help="cap for this run")] = None,
) -> None:
    """Generate articles within the daily AI budget."""
    _bootstrap()
    with session_scope() as session:
        _print(
            jobs.generate_daily_articles(
                session, markets=_markets(market), max_per_run=max_articles
            )
        )


@app.command()
def schedule(market: Annotated[str | None, typer.Option()] = None) -> None:
    """Spread approved articles over the publishing window."""
    _bootstrap()
    with session_scope() as session:
        _print(jobs.schedule_publications(session, markets=_markets(market)))


@app.command("publish-queue")
def publish_queue(limit: Annotated[int, typer.Option()] = 5) -> None:
    """Publish everything that is due."""
    _bootstrap()
    with session_scope() as session:
        _print(jobs.process_publication_queue(session, limit=limit))


@app.command("publish-test")
def publish_test(article_id: int) -> None:
    """Publish one article to the test channel."""
    _bootstrap()
    from app.db.models import Article
    from app.services.workflow import ArticleWorkflow

    with session_scope() as session:
        article = session.get(Article, article_id)
        if article is None:
            raise typer.BadParameter(f"article {article_id} not found")
        result = ArticleWorkflow(session).publish_test(article)
        typer.secho(result.message, fg=typer.colors.GREEN if result.ok else typer.colors.RED)


@app.command()
def cycle() -> None:
    """Run sync → discover → generate → schedule."""
    _bootstrap()
    for report in jobs.run_daily_cycle():
        _print(report)


@app.command()
def coverage(market: Annotated[str | None, typer.Option()] = None) -> None:
    """Show how much catalogue material is still unwritten."""
    _bootstrap()
    with session_scope() as session:
        reports = jobs.coverage_report(session, markets=_markets(market))
    for code, report in reports.items():
        colour = typer.colors.YELLOW if report.exhausted else typer.colors.GREEN
        typer.secho(
            f"{code.upper()}: {report.usable_candidates} topics left, "
            f"{report.used_topics} written, {report.available_products} products",
            fg=colour,
        )
        typer.echo(f"  {report.reason}")
        if report.below_threshold:
            typer.echo(
                f"  {report.below_threshold} candidates are below MIN_TOPIC_SCORE and "
                "will not be written"
            )
        if report.last_new_product_at:
            typer.echo(
                f"  newest product seen: {report.last_new_product_at:%Y-%m-%d} "
                f"({report.new_products_7d} added in the last 7 days)"
            )


@app.command()
def budget() -> None:
    """Show today's AI budget."""
    _bootstrap()
    from app.ai.budget import BudgetManager

    with session_scope() as session:
        manager = BudgetManager(session)
        snapshot = manager.snapshot()
        typer.echo(
            json.dumps(
                {
                    "date": snapshot.spend_date.isoformat(),
                    "budget_usd": snapshot.budget_usd,
                    "spent_usd": snapshot.spent_usd,
                    "reserved_usd": snapshot.reserved_usd,
                    "remaining_usd": snapshot.remaining_usd,
                    "generated": snapshot.generated,
                    "average_article_cost_usd": snapshot.average_article_cost_usd,
                    "plan": manager.plan_daily_generation(),
                },
                indent=2,
            )
        )


@app.command("slack-check")
def slack_check(
    post: Annotated[
        bool, typer.Option("--post", help="Send a test message to SLACK_CHANNEL")
    ] = False,
) -> None:
    """Verify Slack credentials. Does not spend AI budget.

    Slack turns itself on when the bot token, signing secret and channel are all
    set, even if ``SLACK_ENABLED`` was left at the default false.
    """
    _bootstrap()
    from app.slack import blocks as sb
    from app.slack.client import SlackClient, SlackError

    settings = get_settings()
    token_ok = bool(settings.slack_bot_token)
    secret_ok = bool(settings.slack_signing_secret)
    channel = (settings.slack_channel or "").strip()

    typer.echo(f"SLACK_ENABLED:         {'true' if settings.slack_enabled else 'false'}")
    typer.echo(f"SLACK_BOT_TOKEN:       {'set' if token_ok else 'MISSING'}")
    typer.echo(f"SLACK_SIGNING_SECRET:  {'set' if secret_ok else 'MISSING'}")
    typer.echo(f"SLACK_CHANNEL:         {channel or 'MISSING'}")
    typer.echo(f"active:                {'yes' if settings.slack_active else 'no'}")

    if not token_ok:
        typer.secho(
            "\nПоложите SLACK_BOT_TOKEN в `wgt secrets set` или в Cursor Secrets. "
            "Не пишите токен в чат.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    client = SlackClient(settings)
    try:
        identity = client.auth_test()
        bot = identity.get("user") or identity.get("bot_id") or "?"
        team = identity.get("team") or identity.get("url") or "?"
        typer.secho(f"\nauth.test: ok  bot={bot}  workspace={team}", fg=typer.colors.GREEN)
        if post:
            if not channel:
                typer.secho(
                    "SLACK_CHANNEL не задан — тестовое сообщение не отправить",
                    fg=typer.colors.RED,
                )
                raise typer.Exit(code=1)
            client.post_message(
                blocks=sb.connected_card(
                    bot_name=str(bot), team=str(team), admin_url=settings.admin_base_url
                ),
                text="WeGoTrip Content Engine подключён",
            )
            typer.secho(f"test message posted to {channel}", fg=typer.colors.GREEN)
        elif not settings.slack_active:
            missing = []
            if not channel:
                missing.append("SLACK_CHANNEL")
            if not secret_ok:
                missing.append("SLACK_SIGNING_SECRET")
            hint = " и ".join(missing) if missing else "SLACK_ENABLED=true"
            typer.secho(
                f"\nТокен принят, но интеграция ещё выключена: задайте {hint}.",
                fg=typer.colors.YELLOW,
            )
    except SlackError as exc:
        typer.secho(f"\nauth.test failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    host = settings.admin_base_url.rstrip("/")
    if host.startswith("http"):
        typer.echo("\nПосле деплоя в Slack App укажите:")
        typer.echo(f"  Interactivity Request URL: {host}/slack/interactions")
        typer.echo(f"  Slash Command /wegotrip:   {host}/slack/commands")


@app.command("check-telegram")
def check_telegram() -> None:
    """Verify the bot token and that the bot can see its channels."""
    _bootstrap()
    from app.telegram.api import build_telegram_client

    settings = get_settings()
    client = build_telegram_client(settings)
    try:
        typer.echo(f"bot: {json.dumps(client.get_me())}")
        for label, channel in (
            ("EN", settings.telegram_en_channel),
            ("RU", settings.telegram_ru_channel),
            ("TEST", settings.telegram_test_channel),
        ):
            if not channel:
                typer.secho(f"{label}: not configured", fg=typer.colors.YELLOW)
                continue
            try:
                chat = client.get_chat(channel)
                typer.secho(f"{label} {channel}: ok (id={chat.get('id')})", fg=typer.colors.GREEN)
            except Exception as exc:
                typer.secho(f"{label} {channel}: {exc}", fg=typer.colors.RED)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


secrets_app = typer.Typer(help="Encrypted credential storage", no_args_is_help=True)
app.add_typer(secrets_app, name="secrets")


def _store():
    from app.security.secrets import SecretStore

    return SecretStore()


@secrets_app.command("init")
def secrets_init() -> None:
    """Create the master key if it does not exist yet."""
    _bootstrap()
    store = _store()
    store.set("ADMIN_PASSWORD", store.get("ADMIN_PASSWORD") or "change-me")
    typer.secho(f"Store:      {store.path}", fg=typer.colors.GREEN)
    typer.secho(f"Master key: {store.key_source}", fg=typer.colors.GREEN)
    typer.echo("\nBack the master key up somewhere safe. Without it the store cannot be read.")


@secrets_app.command("set")
def secrets_set(
    name: Annotated[str, typer.Argument(help="e.g. OPENAI_API_KEY")],
    value: Annotated[
        str | None, typer.Option(help="Omit to be prompted without echoing to the terminal")
    ] = None,
) -> None:
    """Store one credential, encrypted."""
    _bootstrap()
    secret = value or typer.prompt(f"{name.upper()} value", hide_input=True)
    _store().set(name, secret)
    typer.secho(f"{name.upper()} stored, encrypted", fg=typer.colors.GREEN)


@secrets_app.command("list")
def secrets_list() -> None:
    """Show which credentials are stored, masked."""
    _bootstrap()
    from app.config import secrets_status

    status = secrets_status()
    typer.echo(f"Store:      {status['store_path']}")
    typer.echo(f"Master key: {status['key_source']}\n")

    store = _store()
    encrypted = status["encrypted"]
    if isinstance(encrypted, list) and encrypted:
        typer.secho("Encrypted:", fg=typer.colors.GREEN)
        for name in encrypted:
            value = store.get(name) or ""
            masked = f"{value[:4]}…{value[-4:]}" if len(value) > 12 else "***"
            typer.echo(f"  {name} = {masked}")
    else:
        typer.secho("Encrypted: nothing stored yet", fg=typer.colors.YELLOW)

    plaintext = status["plaintext_env"]
    if isinstance(plaintext, list) and plaintext:
        typer.secho(
            "\nStill in plaintext environment: " + ", ".join(plaintext), fg=typer.colors.YELLOW
        )
        typer.echo("Move them in with `wgt secrets import-env .env`.")


@secrets_app.command("rm")
def secrets_rm(name: Annotated[str, typer.Argument()]) -> None:
    """Remove one credential from the store."""
    _bootstrap()
    if _store().delete(name):
        typer.secho(f"{name.upper()} removed", fg=typer.colors.GREEN)
    else:
        typer.secho(f"{name.upper()} was not stored", fg=typer.colors.YELLOW)


@secrets_app.command("import-env")
def secrets_import_env(
    path: Annotated[pathlib.Path, typer.Argument(help="Plaintext .env to migrate")],
) -> None:
    """Move credentials from a plaintext .env into the encrypted store."""
    _bootstrap()
    if not path.exists():
        raise typer.BadParameter(f"{path} not found")
    imported = _store().import_env_file(path)
    if not imported:
        typer.secho("No known credentials found in the file", fg=typer.colors.YELLOW)
        return
    typer.secho(f"Imported and encrypted: {', '.join(imported)}", fg=typer.colors.GREEN)
    typer.secho(
        f"\nNow delete those lines from {path} — they are still in plaintext there.",
        fg=typer.colors.YELLOW,
    )


@secrets_app.command("rotate-key")
def secrets_rotate_key() -> None:
    """Re-encrypt the store under a new master key."""
    _bootstrap()
    store = _store()
    key = store.rotate_key()
    typer.secho("Store re-encrypted under a new master key", fg=typer.colors.GREEN)
    if os.getenv("SECRETS_MASTER_KEY"):
        typer.secho("\nUpdate SECRETS_MASTER_KEY to:", fg=typer.colors.YELLOW)
        typer.echo(key)
    else:
        typer.echo(f"New key written to {store.key_path}")


@app.command("telegram-chats")
def telegram_chats() -> None:
    """List chats the bot can see, with the ids to put into configuration.

    A private channel has no @username, so it is addressed by its numeric `-100…` id.
    Telegram reveals that id only after the bot has seen an event in the channel: add
    the bot as an administrator and post anything there, then run this command.
    """
    _bootstrap()
    from app.telegram.api import build_telegram_client

    client = build_telegram_client(get_settings())
    try:
        chats = client.discover_chats()
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    if not chats:
        typer.secho(
            "Не видно ни одного чата. Добавьте бота администратором в канал и отправьте "
            "туда любое сообщение, затем повторите команду.",
            fg=typer.colors.YELLOW,
        )
        return

    for chat in chats:
        name = chat.get("title") or chat.get("username") or "без названия"
        username = f"@{chat['username']}" if chat.get("username") else "приватный"
        typer.secho(
            f"{chat['id']}  {name}  ({chat.get('type')}, {username})", fg=typer.colors.GREEN
        )
    typer.echo(
        "\nВставьте нужный id в TELEGRAM_TEST_CHANNEL / TELEGRAM_EN_CHANNEL / "
        "TELEGRAM_RU_CHANNEL — числовой id работает так же, как @username."
    )


@app.command("import-conversions")
def import_conversions(path: Annotated[pathlib.Path, typer.Argument()]) -> None:
    """Import orders from the affiliate back office.

    CSV columns: order_id, article_public_id, market, product_id, gmv, revenue,
    currency, occurred_at (ISO 8601).
    """
    _bootstrap()
    from sqlalchemy import select

    from app.db.models import Article, ConversionEvent

    imported = 0
    with session_scope() as session, path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            order_id = (row.get("order_id") or "").strip()
            if not order_id:
                continue
            existing = session.scalar(
                select(ConversionEvent).where(ConversionEvent.external_order_id == order_id)
            )
            if existing is not None:
                continue
            article = None
            public_id = (row.get("article_public_id") or "").strip()
            if public_id:
                article = session.scalar(select(Article).where(Article.public_id == public_id))
            occurred = row.get("occurred_at")
            session.add(
                ConversionEvent(
                    external_order_id=order_id,
                    article_id=article.id if article else None,
                    market=(row.get("market") or (article.market if article else "en")),
                    product_external_id=(row.get("product_id") or None),
                    gmv=float(row.get("gmv") or 0),
                    revenue=float(row.get("revenue") or 0),
                    currency_code=(row.get("currency") or "EUR"),
                    source="csv",
                    occurred_at=dt.datetime.fromisoformat(occurred)
                    if occurred
                    else dt.datetime.now(dt.UTC),
                    payload=dict(row),
                )
            )
            imported += 1
    typer.secho(f"imported {imported} conversions", fg=typer.colors.GREEN)


@app.command()
def worker() -> None:
    """Run the scheduler in the foreground."""
    _bootstrap()
    runner = SchedulerRunner(blocking=True)
    typer.echo("scheduler started; jobs:")
    for job in runner.scheduler.get_jobs():
        typer.echo(f"  {job.id}: {job.trigger}")
    try:
        runner.start()
    except (KeyboardInterrupt, SystemExit):
        runner.shutdown()


@app.command()
def doctor() -> None:
    """Check configuration and connectivity without spending anything."""
    _bootstrap()
    settings = get_settings()
    checks: list[tuple[str, bool, str]] = []

    checks.append(
        ("database_url", bool(settings.database_url), settings.database_url.split("@")[-1])
    )
    checks.append(("openai_api_key", bool(settings.openai_api_key), settings.llm_provider))
    checks.append(
        (
            "telegram_bot_token",
            bool(settings.telegram_bot_token),
            "dry run" if settings.telegram_dry_run else "live",
        )
    )
    checks.append(
        (
            "telegram_test_channel",
            bool(settings.telegram_test_channel),
            settings.telegram_test_channel or "MISSING",
        )
    )
    checks.append(
        ("referer_id", settings.wegotrip_referer_id == "435", settings.wegotrip_referer_id)
    )
    checks.append(
        (
            "auto_publish_off",
            not (settings.auto_publish_en or settings.auto_publish_ru),
            "review mode",
        )
    )
    checks.append(
        (
            "generated_covers_off",
            not settings.allow_generated_covers,
            str(settings.allow_generated_covers),
        )
    )
    slack_bits = []
    if settings.slack_bot_token:
        slack_bits.append("token")
    if settings.slack_signing_secret:
        slack_bits.append("signing")
    if settings.slack_channel:
        slack_bits.append(settings.slack_channel)
    checks.append(
        (
            "slack",
            settings.slack_active,
            "active (" + ", ".join(slack_bits) + ")" if slack_bits else "off",
        )
    )

    try:
        with session_scope() as session:
            from sqlalchemy import text

            session.execute(text("SELECT 1"))
        checks.append(("database_connection", True, "ok"))
    except Exception as exc:
        checks.append(("database_connection", False, str(exc)[:80]))

    from app.config import secrets_status

    status = secrets_status()
    encrypted = status["encrypted"]
    plaintext = status["plaintext_env"]
    checks.append(
        (
            "secrets_encrypted",
            bool(encrypted),
            f"{len(encrypted) if isinstance(encrypted, list) else 0} in {status['store_path']}",
        )
    )
    if isinstance(plaintext, list) and plaintext:
        checks.append(
            ("secrets_plaintext", False, ", ".join(plaintext) + " — run `wgt secrets import-env`")
        )

    for name, ok, detail in checks:
        colour = typer.colors.GREEN if ok else typer.colors.YELLOW
        typer.secho(f"{'✓' if ok else '!'} {name}: {detail}", fg=colour)


if __name__ == "__main__":
    app()
