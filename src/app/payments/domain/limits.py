"""Every payment-path timing and limit in one place (VS-024 plan 3.8, D14). Pure: values
only. Ordering's domain rules take these as parameters and never import this module."""

from datetime import timedelta

# Provider calls (VS-023): create_payment and query_status are both bounded by this.
PROVIDER_TIMEOUT_SECONDS = 10.0
MOCK_REDIS_TIMEOUT_SECONDS = PROVIDER_TIMEOUT_SECONDS
MOCK_STATE_TTL_SECONDS = 7 * 24 * 3600

# Webhook receipt (VS-023, ADR-032 d15).
WEBHOOK_MAX_BODY_BYTES = 64 * 1024
WEBHOOK_UNVERIFIED_LIMIT = 30
WEBHOOK_VERIFIED_LIMIT = 600
WEBHOOK_WINDOW_SECONDS = 60

# Jobs.
VERIFY_BATCH_SIZE = 50
RECONCILE_MIN_AGE = timedelta(minutes=5)
RECONCILE_PAGE_SIZE = 50
RELEASE_PAGE_SIZE = 50
RECONCILE_CRON_MINUTES = frozenset({0, 15, 30, 45})
RECONCILE_CRON_SECOND = 30
RELEASE_CRON_MINUTES = frozenset(range(2, 60, 5))
RELEASE_CRON_SECOND = 45
JOB_RUN_DEADLINE_SECONDS = 240.0
PROVIDER_BREAKER_FAILURES = 3

# Recovery windows and alert repetition.
STUCK_AFTER = timedelta(hours=1)
MANUAL_RELEASE_GRACE = timedelta(hours=24)
ALERT_REPEAT_PER_PAYMENT = timedelta(hours=24)
ALERT_REPEAT_PER_PROVIDER = timedelta(hours=1)

# Rate limits: (requests, window seconds); per user for checkout and retry, per admin else.
CHECKOUT_RATE_LIMIT = 30
CHECKOUT_RATE_WINDOW_SECONDS = 3600
RETRY_RATE_LIMIT = 10
RETRY_RATE_WINDOW_SECONDS = 3600
CONFIRM_RATE_LIMIT = 30
RECONCILE_RATE_LIMIT = 60
RELEASE_RATE_LIMIT = 30
ADMIN_ACTION_WINDOW_SECONDS = 3600

# Admin reads and free-text fields.
ADMIN_PAGE_DEFAULT = 20
ADMIN_PAGE_MAX = 100
REASON_MIN = 10
REASON_MAX = 1000

# Refunds (VS-030 plan 2, 5): per administrator per hour, and the request bounds.
REFUND_WRITE_RATE_LIMIT = 60
REFUND_READ_RATE_LIMIT = 300
REFUND_MAX_ITEMS = 50
REFUND_MAX_AMOUNT_CENTS = 1_000_000_000
REFUND_TEXT_MAX = 1000
SETTLEMENT_REFERENCE_MAX = 200
DISPUTE_REFERENCE_MAX = 200  # ck_chargebacks_dispute_reference
