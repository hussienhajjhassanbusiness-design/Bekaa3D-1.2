"""settings table and seeded registry

Revision ID: de1d8a23512f
Revises: 6bb89f11d84b
Create Date: 2026-09-12 03:48:14.042499

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "de1d8a23512f"
down_revision: str | None = "6bb89f11d84b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# A minimal table definition for the seed. Deliberately declared here rather
# than imported from `app.platform.infrastructure.models`: a migration is frozen
# history, and one that reads live model code changes meaning whenever that code
# changes.
_settings = sa.table(
    "settings",
    sa.column("key", sa.Text),
    # Declared as the enum, not as Text. asyncpg binds parameters with an
    # explicit type, so a Text column here sends `$2::VARCHAR` and PostgreSQL
    # refuses it: "column type is of type setting_type but expression is of type
    # character varying". It will not implicitly cast varchar to an enum.
    #
    # `create_type=False` because `create_table` above has already created the
    # type; without it this declaration would try to emit a second CREATE TYPE.
    sa.column(
        "type",
        postgresql.ENUM(
            "boolean",
            "integer",
            "string",
            "money",
            "duration",
            "json",
            name="setting_type",
            create_type=False,
        ),
    ),
    # `none_as_null=False` so a Python None is written as the JSON value `null`
    # rather than SQL NULL - the column is NOT NULL, and four of these settings
    # are legitimately unconfigured.
    sa.column("value", postgresql.JSONB(none_as_null=False)),
    sa.column("description", sa.Text),
)

# The twelve settings SRS 15.4 requires, with the V1 defaults.
#
# Written out literally, and *not* generated from
# `app.platform.domain.settings_registry`. That is the important part: this
# migration must always do what it did the day it was written. If it read the
# registry, then editing a default in code would silently rewrite history - a
# database created next year would be seeded differently from one created
# today, from the same migration. Changing a default later is a new migration
# (for fresh deployments) or a PATCH (for running ones).
#
# The SRS specifies none of these numbers; it says each is "configurable" and
# stops there. They are V1 product decisions.
_SEED: tuple[dict[str, Any], ...] = (
    {
        "key": "accepting_orders",
        "type": "boolean",
        # Closed until an administrator opens the shop: a fresh deployment has
        # no catalogue, no shipping zones and no verified payment provider.
        "value": False,
        "description": (
            "Global kill switch. False blocks new checkout with 503 ORDERS_PAUSED; "
            "payments already in flight are unaffected."
        ),
    },
    {
        "key": "offer_response_window",
        "type": "duration",
        "value": 172_800,  # 48 hours
        "description": (
            "Seconds the party whose turn it is has to respond before an offer expires."
        ),
    },
    {
        "key": "offer_checkout_window",
        "type": "duration",
        "value": 86_400,  # 24 hours
        "description": "Seconds an accepted offer stays purchasable at its frozen price.",
    },
    {
        "key": "offer_rejection_cooldown",
        "type": "duration",
        "value": 604_800,  # 7 days
        "description": (
            "Seconds after a rejection before the same customer may offer on that product again."
        ),
    },
    {
        "key": "minimum_offer_percentage",
        "type": "integer",
        "value": 70,
        "description": "Offer floor as a whole percentage of list price.",
    },
    {
        "key": "checkout_hold_period",
        "type": "duration",
        "value": 1_800,  # 30 minutes
        "description": "Seconds an unpaid checkout is held before automatic cancellation.",
    },
    {
        "key": "unverified_account_purge_period",
        "type": "duration",
        # 30 days: exactly what purge_unverified_accounts used from a
        # source-code constant before VS-007, so this deployment moves the
        # control into the database without changing behaviour.
        "value": 2_592_000,
        "description": "Seconds after which a never-verified account is physically deleted.",
    },
    {
        "key": "daily_download_cap",
        "type": "integer",
        "value": 20,
        "description": "Download attempts allowed per authenticated customer per UTC day.",
    },
    {
        "key": "free_shipping_threshold",
        "type": "money",
        # BR-076 calls this optional, so "off" must be representable; any
        # number here would be a business decision nobody has made.
        "value": None,
        "description": (
            "Order value at or above which delivery is free. JSON null disables free shipping."
        ),
    },
    {
        "key": "pickup_address",
        "type": "string",
        # Awaiting the client (SRS 30.2). Null rather than a placeholder: this
        # is served publicly, and a plausible fake address is worse than a
        # visibly absent one.
        "value": None,
        "description": "Workshop address shown at checkout and in the ready-for-pickup notice.",
    },
    {
        "key": "pickup_hours",
        "type": "string",
        "value": None,
        "description": "Workshop opening hours, shown alongside the pickup address.",
    },
    {
        "key": "whatsapp_number",
        "type": "string",
        "value": None,
        "description": "Business WhatsApp number in canonical E.164 for click-to-chat.",
    },
)


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "settings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "boolean", "integer", "string", "money", "duration", "json", name="setting_type"
            ),
            nullable=False,
        ),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    # ### end Alembic commands ###

    # Seeded here rather than at application startup, because "the settings
    # exist immediately after deployment" is exactly what a migration
    # guarantees: `alembic upgrade head` runs before the new code serves
    # traffic. Startup seeding races when several workers boot at once, and a
    # separate script is a step somebody eventually forgets.
    #
    # ON CONFLICT DO NOTHING makes it safe to re-run: on any recovery path that
    # replays this migration against a database that already has these rows, an
    # administrator's edited value is left exactly as they set it. An upsert
    # would silently reset business parameters during a recovery, which is the
    # one thing a seed must never do.
    op.execute(
        postgresql.insert(_settings)
        .values(list(_SEED))
        .on_conflict_do_nothing(index_elements=["key"])
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("settings")
    # ### end Alembic commands ###

    # Autogenerate does not emit this, and its absence is the B01 bug this
    # project has already been bitten by once. `sa.Enum(...)` inside
    # create_table issues an implicit CREATE TYPE, but drop_table issues only
    # DROP TABLE - SQLAlchemy cannot know whether another table still uses the
    # type. Left behind, `setting_type` makes the next upgrade fail with
    # DuplicateObjectError before creating a single table.
    #
    # Dropped here, in the migration that creates it, and only after the table
    # that uses it is gone.
    sa.Enum(name="setting_type").drop(op.get_bind(), checkfirst=True)
