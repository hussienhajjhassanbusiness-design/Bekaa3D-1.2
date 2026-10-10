Non-Functional Requirements
Category	Target	Why / source
Profile	Profile C	Payments, STL delivery tracking, refunds, concurrency, background jobs, and recovery-critical workflows
Peak load	RPS: TBD; 200 concurrent users without degradation	The SRS defines concurrent usage but does not provide an RPS estimate
Catalogue scale	10,000 products without index redesign	SRS NFR-07
Largest table at 1 year	TBD rows	No order, audit, webhook, or notification volume forecast is provided
Largest table at 3 years	TBD rows	Must be estimated from measured production activity
Catalogue latency	p95 < 500 ms	SRS NFR-01
Search latency	p95 < 800 ms	SRS NFR-02
Checkout latency	< 2 seconds, excluding payment redirect	SRS NFR-03
Availability	99% monthly	Equivalent to approximately 432 minutes of downtime in a 30-day month
Database RPO	≤ 5 minutes	Continuous WAL archiving
File RPO	≤ 24 hours	Daily and on-upload snapshots
RTO	≤ 4 hours	Documented restoration runbook
Audit-log hot retention	24 months	Older records are archived
Account erasure	Anonymization: yes; hard deletion: no for retained financial/delivery records	Required for accounting and referential integrity
Unverified accounts	Configurable purge period	Exact duration is not fixed by the SRS
Attachment retention	Configurable; numeric value TBD	Bring Your Idea attachment period remains a design decision
Accessibility	WCAG 2.1 AA target	SRS NFR-13
Localization	English only for V1	No RTL/LTR duality; single locale, LTR only
Timestamp standard	100% UTC storage	SRS NFR-12
Payment verification	100% of online payments independently verified before producing goods or sending STL files; cash recorded only by the administrator at handover	Core business and security invariant (ADR-024)
Webhook idempotency	Zero duplicate payment applications from repeated provider events	Unique provider event identifiers
Checkout idempotency	Zero duplicate orders for the same valid idempotency request	Required checkout invariant
Backup verification	Daily	Detects silently unusable backups
Restore drill	Quarterly	Validates the recovery runbook
Payment reconciliation	Every 15 minutes	Limits the duration of unresolved missed callbacks
Email-outbox dispatch	Every 1 minute	Verification email is critical to account use
Disk alert threshold	80% used	Database and private uploads share the server volume
Compliance	No named regulatory regime specified	Privacy, data-rights, accounting, security, terms, and refund obligations still apply
Online payment provider SLA	TBD; provider undecided (SRS §30.4)	Availability, rate limits, callback signatures, query API, refunds, and sandbox terms are not confirmed
Email provider SLA	TBD	Provider remains an open client decision
Captcha integration	Provider TBD	Required for public forms
Courier integration	None in V1	Fulfillment is manual; the courier prices and collects delivery and collects cash on delivery
Deployment	Single VPS using Docker Compose	Deliberate V1 infrastructure limit
Monitoring	Continuous uptime, error, host, cron, payment, outbox, and disk monitoring	Required to detect silent operational failure
Security testing	All protected routes included in an IDOR and authorization sweep	Required by SRS testing strategy
Concurrency testing	Checkout, callback, cancellation, start printing, cash handover, payment, and offer races tested	Required by SRS testing strategy

The performance, availability, scale, recovery, language, UTC, and accessibility targets above come directly from the SRS.

Required measurements before production

The following unresolved values must be measured or approved before final capacity testing:

Expected normal and peak requests per second
Orders per day, and the share paid in cash
Cash-on-delivery refusal rate
Payment callbacks per day
STL lines sold per day (sizes the manual delivery workload)
Audit events per order
Expected product-image storage growth
Largest-table row estimates after one and three years
Bring Your Idea attachment-retention period
Unverified-account purge period
Online provider API rate limits and availability expectations
Transactional email-provider delivery SLA
Maximum acceptable payment-reconciliation delay
Final legal retention requirements
Fixed production-launch date