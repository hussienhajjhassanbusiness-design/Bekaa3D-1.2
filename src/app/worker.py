import sys
from typing import Any

from arq.connections import RedisSettings
from arq.worker import run_worker

from app.core import models as _models  # noqa: F401 - registers models onto Base.metadata
from app.core.config import get_settings
from app.core.database import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.integrations.email.factory import get_email_provider
from app.jobs.registry import CRON_JOBS, FUNCTIONS


def _redis_settings() -> RedisSettings:
    """Redis connection settings with retries enabled.

    arq's defaults give up on a timed-out command, and the worker's poll loop
    then dies on the first blip. Retrying instead means a Redis restart that
    finishes inside the retry budget is survived rather than being fatal.
    """
    settings = RedisSettings.from_dsn(get_settings().redis_url)
    settings.conn_retries = 10
    settings.conn_retry_delay = 2
    settings.retry_on_timeout = True
    return settings


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    settings = get_settings()

    # Resolve the email provider once, at startup, purely so a bad
    # EMAIL_PROVIDER value kills the worker here instead of at the top of every
    # dispatch_outbox run. Failing inside the job aborts it before a single row
    # is claimed, so no message ever records an attempt or an error - the queue
    # just stops, indistinguishable from an idle one. Failing at startup is loud
    # and the container restart loop makes it impossible to miss.
    get_email_provider(settings)

    engine = make_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


class WorkerSettings:
    # `functions` makes jobs directly enqueueable (tests, manual triggers);
    # `cron_jobs` (jobs/registry.py) gives each job its standing schedule.
    # arq's cron `unique=True` default means only one fires per tick even if
    # multiple worker replicas share this queue.
    functions = FUNCTIONS
    cron_jobs = CRON_JOBS
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = _redis_settings()


def main() -> None:
    """Entrypoint that makes a dead worker a dead process.

    `arq ... --watch` must not be used to run this service. arq's watch mode
    does `loop.create_task(worker.async_run())` and then blocks on the file
    watcher without ever awaiting that task (arq/cli.py). If the worker's poll
    loop raises - a Redis outage is enough - the exception is stored on a task
    nobody retrieves, the process stays alive blocked on the watcher, and cron
    never fires again. The container looks healthy and silently stops sending
    every transactional email in the system.

    `run_worker` awaits the task, so the same failure ends the process, and
    Docker's `restart: unless-stopped` brings it straight back. Recovering by
    dying is the point: an outage becomes a restart instead of a permanent,
    invisible stall.
    """
    try:
        run_worker(WorkerSettings)  # type: ignore[arg-type]
    except Exception:
        # Logged by arq already; the exit code is what the restart policy reads.
        sys.exit(1)


if __name__ == "__main__":
    main()
