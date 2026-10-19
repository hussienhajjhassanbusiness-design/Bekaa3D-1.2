from arq import cron
from arq.cron import CronJob
from arq.typing import WorkerCoroutine

from app.jobs.outbox import dispatch_outbox
from app.jobs.partitions import ensure_partitions
from app.jobs.purge_expired_attachments import purge_expired_attachments
from app.jobs.purge_idempotency import purge_expired_idempotency_records
from app.jobs.purge_security_records import purge_expired_security_records
from app.jobs.purge_unverified import purge_unverified_accounts
from app.jobs.reap_orphan_files import reap_orphan_files
from app.jobs.reconcile_payments import reconcile_payments
from app.jobs.release_stale_checkouts import release_stale_checkouts
from app.jobs.rotate_ip_salt import rotate_ip_salt
from app.jobs.verify_payments import verify_payments
from app.payments.domain.limits import (
    RECONCILE_CRON_MINUTES,
    RECONCILE_CRON_SECOND,
    RELEASE_CRON_MINUTES,
    RELEASE_CRON_SECOND,
)

FUNCTIONS: list[WorkerCoroutine] = [
    dispatch_outbox,
    purge_unverified_accounts,
    ensure_partitions,
    reap_orphan_files,
    rotate_ip_salt,
    purge_expired_security_records,
    purge_expired_attachments,
    verify_payments,
    purge_expired_idempotency_records,
    reconcile_payments,
    release_stale_checkouts,
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
    # VS-046: daily; a missed day is harmless, the next run takes the backlog.
    cron(purge_expired_security_records, hour=3, minute=29, second=0),
    # VS-034 / SRS 23: daily; a missed day is harmless, the next run takes the backlog.
    cron(purge_expired_attachments, hour=3, minute=35, second=0),
    # VS-023: the fallback for verification lost after a webhook's 200; every minute.
    cron(verify_payments, second=0, run_at_startup=True),
    # VS-023 / SRS 7.5: claims live 24 h; daily, the next run takes any backlog.
    cron(purge_expired_idempotency_records, hour=3, minute=53, second=0),
    # VS-024: missed callbacks and stuck attempts; the provider is asked, never assumed.
    cron(
        reconcile_payments,
        minute=set(RECONCILE_CRON_MINUTES),
        second=RECONCILE_CRON_SECOND,
        run_at_startup=True,
    ),
    # VS-024: unpaid checkouts past their hold, released only on an explicit answer.
    cron(
        release_stale_checkouts,
        minute=set(RELEASE_CRON_MINUTES),
        second=RELEASE_CRON_SECOND,
        run_at_startup=True,
    ),
]
