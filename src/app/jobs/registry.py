from arq import cron
from arq.cron import CronJob
from arq.typing import WorkerCoroutine

from app.jobs.outbox import dispatch_outbox
from app.jobs.partitions import ensure_partitions
from app.jobs.purge_unverified import purge_unverified_accounts
from app.jobs.reap_orphan_files import reap_orphan_files
from app.jobs.rotate_ip_salt import rotate_ip_salt

FUNCTIONS: list[WorkerCoroutine] = [
    dispatch_outbox,
    purge_unverified_accounts,
    ensure_partitions,
    reap_orphan_files,
    rotate_ip_salt,
]

CRON_JOBS: list[CronJob] = [
    # Every minute, per SRS 23. run_at_startup catches up on anything queued
    # while the worker was down.
    cron(dispatch_outbox, second=0, run_at_startup=True),
    # Retention work, not user-facing: once a day, off the hour so it does not
    # contend with the minute-by-minute outbox sweep.
    cron(purge_unverified_accounts, hour=3, minute=17, second=0),
    # SRS 23 / ADR-015: monthly, plus at every worker start, so a worker that was
    # down over a month boundary catches up before anything needs the partition.
    cron(ensure_partitions, day=1, hour=0, minute=7, second=0, run_at_startup=True),
    # SRS 23: daily reconciliation of stored files against product_images (VS-014).
    cron(reap_orphan_files, hour=3, minute=41, second=0),
    # SRS 23 / ADR-028: daily check plus at worker start; rotates once per UTC month.
    cron(rotate_ip_salt, hour=0, minute=23, second=0, run_at_startup=True),
]
