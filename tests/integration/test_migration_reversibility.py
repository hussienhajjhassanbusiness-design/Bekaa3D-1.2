"""Full-chain migration reversibility (B01).

`alembic downgrade -1` then `upgrade head` - the check CONTRIBUTING.md asks for
before merging a migration PR - would not have caught B01: it only steps back
over the newest revision, and the migrations that create enum types sit further
down the chain. Only a walk to `base` and back exercises them, which is what
SRS 24.7 means by "migration reversibility check".
"""

import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

CART_REVISION = "bde6135b2538"
BYI_REVISION = "26d5d039d72c"
ORDERS_REVISION = "03a4730dd046"
CAPTURED_REVISION = "00ce1ce252a6"
CASH_REVISION = "fcd589e89e59"
REFUNDS_REVISION = "c01e53ab3e0f"
REVIEWS_REVISION = "eeed201dcfd2"
EXPECTED_ENUMS = {"user_role", "outbox_status", "setting_type", "notification_type"}


@pytest.mark.integration
def test_full_downgrade_and_upgrade_round_trips() -> None:
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        config = Config("alembic.ini")

        async def fetch(query: str) -> set[str]:
            engine = create_async_engine(url)
            async with engine.connect() as conn:
                result = await conn.execute(text(query))
                names = {row[0] for row in result}
            await engine.dispose()
            return names

        enum_query = "SELECT typname FROM pg_type WHERE typtype = 'e'"
        table_query = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"

        command.upgrade(config, "head")
        assert asyncio.run(fetch(enum_query)) >= EXPECTED_ENUMS

        # VS-022: one head, with the cart migration in its chain (later migrations need no
        # edit here). Stepping back over it drops cart_items before the products unique
        # key its composite FK needs.
        scripts = ScriptDirectory.from_config(config)
        assert len(scripts.get_heads()) == 1, scripts.get_heads()
        chain = {script.revision: script for script in scripts.walk_revisions()}
        assert CART_REVISION in chain
        assert chain[CART_REVISION].down_revision == "75ad58ebd9e5"
        cart_tables = {"carts", "cart_items"}
        id_type_key = "SELECT conname FROM pg_constraint WHERE conname = 'uq_products_id_type'"
        assert cart_tables <= asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(id_type_key)) == {"uq_products_id_type"}
        command.downgrade(config, f"{CART_REVISION}-1")
        assert cart_tables.isdisjoint(asyncio.run(fetch(table_query)))
        assert asyncio.run(fetch(id_type_key)) == set()
        assert "product_type" in asyncio.run(fetch(enum_query)), "products still owns it"
        command.upgrade(config, "head")
        assert cart_tables <= asyncio.run(fetch(table_query))

        # VS-046: stepping back over 75ad58ebd9e5 drops its table and its two settings.
        retention_keys = (
            "SELECT key FROM settings WHERE key IN "
            "('security_token_retention_period', 'session_retention_period')"
        )
        assert len(asyncio.run(fetch(retention_keys))) == 2
        command.downgrade(config, "75ad58ebd9e5-1")
        assert "ip_hash_salts" not in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(retention_keys)) == set()
        command.upgrade(config, "head")

        # VS-034: stepping back over 26d5d039d72c drops both tables, the setting, its enum
        # types, and rebuilds notification_type without `custom_request`.
        byi_tables = {"custom_requests", "custom_request_attachments"}
        notification_values = (
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'notification_type'"
        )
        assert byi_tables <= asyncio.run(fetch(table_query))
        assert "custom_request" in asyncio.run(fetch(notification_values))
        command.downgrade(config, f"{BYI_REVISION}-1")
        assert byi_tables.isdisjoint(asyncio.run(fetch(table_query)))
        assert "custom_request" not in asyncio.run(fetch(notification_values))
        assert {"custom_request_status", "upload_scan_status"}.isdisjoint(
            asyncio.run(fetch(enum_query))
        )
        command.upgrade(config, "head")

        # VS-023 PR A: stepping back to its own parent drops the six tables and eight enum
        # types; product_type stays with products. The head itself is never pinned here.
        assert chain[ORDERS_REVISION].down_revision == BYI_REVISION
        order_tables = {
            "orders",
            "order_items",
            "order_status_history",
            "payments",
            "webhook_events",
            "idempotency_records",
        }
        order_enums = {
            "fulfillment_method",
            "payment_method",
            "cancel_reason",
            "order_source",
            "order_status",
            "order_item_status",
            "payment_status",
            "payment_provider",
        }
        assert order_tables <= asyncio.run(fetch(table_query))
        assert order_enums <= asyncio.run(fetch(enum_query))
        command.downgrade(config, f"{ORDERS_REVISION}-1")
        assert order_tables.isdisjoint(asyncio.run(fetch(table_query)))
        assert order_enums.isdisjoint(asyncio.run(fetch(enum_query)))
        assert "product_type" in asyncio.run(fetch(enum_query)), "products still owns it"
        assert byi_tables <= asyncio.run(fetch(table_query)), "the parent is untouched"
        command.upgrade(config, "head")
        assert order_tables <= asyncio.run(fetch(table_query))

        # VS-024 PR A: stepping back to its own parent drops the two CHECKs, then the two
        # columns; payments itself (03a4730dd046) stays. The head is never pinned here.
        assert chain[CAPTURED_REVISION].down_revision == ORDERS_REVISION
        captured_columns = (
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'payments' "
            "AND column_name IN ('captured_amount_cents', 'captured_currency')"
        )
        captured_checks = (
            "SELECT conname FROM pg_constraint WHERE conrelid = 'payments'::regclass "
            "AND conname IN ('ck_payments_captured_shape', 'ck_payments_captured_when')"
        )
        both_columns = {"captured_amount_cents", "captured_currency"}
        both_checks = {"ck_payments_captured_shape", "ck_payments_captured_when"}
        assert asyncio.run(fetch(captured_columns)) == both_columns
        assert asyncio.run(fetch(captured_checks)) == both_checks
        command.downgrade(config, ORDERS_REVISION)
        assert asyncio.run(fetch(captured_columns)) == set()
        assert asyncio.run(fetch(captured_checks)) == set()
        assert "payments" in asyncio.run(fetch(table_query)), "the parent is untouched"
        command.upgrade(config, "head")
        assert asyncio.run(fetch(captured_columns)) == both_columns
        assert asyncio.run(fetch(captured_checks)) == both_checks

        # VS-028 PR A: stepping back to its own parent (read from the chain, never pinned)
        # drops the block table, the two orders CHECKs and the index, and the three cash
        # settings, and restores free_shipping_threshold as JSON null.
        cash_parent = chain[CASH_REVISION].down_revision
        assert isinstance(cash_parent, str)
        cash_checks = (
            "SELECT conname FROM pg_constraint WHERE conrelid = 'orders'::regclass "
            "AND conname IN ('ck_orders_contact_phone_e164', 'ck_orders_phone_hash_format')"
        )
        cash_index = (
            "SELECT indexname FROM pg_indexes WHERE indexname = 'ix_orders_open_cash_phone'"
        )
        setting_keys = "SELECT key FROM settings"
        cash_keys = {"cash_payment_enabled", "cash_max_open_orders", "cash_max_order_total"}
        free_null = "SELECT jsonb_typeof(value) FROM settings WHERE key = 'free_shipping_threshold'"
        both_cash_checks = {"ck_orders_contact_phone_e164", "ck_orders_phone_hash_format"}
        assert "cash_payment_blocks" in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(cash_checks)) == both_cash_checks
        assert asyncio.run(fetch(cash_index)) == {"ix_orders_open_cash_phone"}
        keys = asyncio.run(fetch(setting_keys))
        assert cash_keys <= keys and "free_shipping_threshold" not in keys
        command.downgrade(config, cash_parent)
        assert "cash_payment_blocks" not in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(cash_checks)) == set()
        assert asyncio.run(fetch(cash_index)) == set()
        keys = asyncio.run(fetch(setting_keys))
        assert cash_keys.isdisjoint(keys) and "free_shipping_threshold" in keys
        assert asyncio.run(fetch(free_null)) == {"null"}
        assert "orders" in asyncio.run(fetch(table_query)), "the parent is untouched"
        command.upgrade(config, "head")
        assert "cash_payment_blocks" in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(cash_checks)) == both_cash_checks
        keys = asyncio.run(fetch(setting_keys))
        assert cash_keys <= keys and "free_shipping_threshold" not in keys

        # VS-030 PR A: stepping back to its own parent (read from the chain, never pinned)
        # drops the four tables, both enum types, the owner FK and the three composite keys.
        refund_parent = chain[REFUNDS_REVISION].down_revision
        assert isinstance(refund_parent, str)
        refund_tables = {"refunds", "refund_items", "chargebacks", "chargeback_items"}
        refund_enums = {"refund_kind", "refund_status"}
        refund_keys = (
            "SELECT conname FROM pg_constraint WHERE conname IN ('uq_orders_id_user',"
            " 'uq_order_items_id_order', 'uq_payments_id_order_provider',"
            " 'fk_order_items_order_owner')"
        )
        all_keys = {
            "uq_orders_id_user",
            "uq_order_items_id_order",
            "uq_payments_id_order_provider",
            "fk_order_items_order_owner",
        }
        assert refund_tables <= asyncio.run(fetch(table_query))
        assert refund_enums <= asyncio.run(fetch(enum_query))
        assert asyncio.run(fetch(refund_keys)) == all_keys
        command.downgrade(config, refund_parent)
        assert refund_tables.isdisjoint(asyncio.run(fetch(table_query)))
        assert refund_enums.isdisjoint(asyncio.run(fetch(enum_query)))
        assert asyncio.run(fetch(refund_keys)) == set()
        assert "payment_provider" in asyncio.run(fetch(enum_query)), "payments still owns it"
        assert {"orders", "payments"} <= asyncio.run(fetch(table_query)), "parents untouched"
        command.upgrade(config, "head")
        assert refund_tables <= asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(refund_keys)) == all_keys

        # VS-036 PR A: stepping back to its own parent (read from the chain, never pinned)
        # drops reviews, its indexes and the order_items badge index; order_items stays.
        reviews_parent = chain[REVIEWS_REVISION].down_revision
        assert isinstance(reviews_parent, str)
        review_indexes = (
            "SELECT indexname FROM pg_indexes WHERE indexname IN ("
            "'uq_reviews_user_product_live', 'ix_reviews_product_visible',"
            " 'ix_reviews_user_live', 'ix_order_items_badge_received')"
        )
        all_review_indexes = {
            "uq_reviews_user_product_live",
            "ix_reviews_product_visible",
            "ix_reviews_user_live",
            "ix_order_items_badge_received",
        }
        assert "reviews" in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(review_indexes)) == all_review_indexes
        command.downgrade(config, reviews_parent)
        assert "reviews" not in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(review_indexes)) == set()
        assert {"order_items", "products"} <= asyncio.run(fetch(table_query)), "parents untouched"
        command.upgrade(config, "head")
        assert "reviews" in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(review_indexes)) == all_review_indexes

        command.downgrade(config, "base")

        # The actual defect: tables went, the enum types stayed, and the next
        # CREATE TYPE then failed with DuplicateObjectError.
        leftover_enums = asyncio.run(fetch(enum_query))
        assert EXPECTED_ENUMS.isdisjoint(leftover_enums), (
            f"enum types survived downgrade: {sorted(EXPECTED_ENUMS & leftover_enums)}"
        )
        leftover_tables = asyncio.run(fetch(table_query))
        assert "users" not in leftover_tables
        assert "email_outbox" not in leftover_tables
        assert "ip_hash_salts" not in leftover_tables
        assert "cart_items" not in leftover_tables
        assert "orders" not in leftover_tables

        # This is the call that used to raise.
        command.upgrade(config, "head")
        assert asyncio.run(fetch(enum_query)) >= EXPECTED_ENUMS

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()


@pytest.mark.integration
async def test_schema_matches_the_frozen_design(db_engine: AsyncEngine) -> None:
    """F06/F07 - two objects database-design.md specifies that the VS-002
    migration omitted.

    Uses the migrated `db_engine` fixture directly rather than rebuilding an
    engine from DATABASE_URL: other modules in the suite reassign that variable,
    so reading it here made the test depend on execution order.
    """
    async with db_engine.connect() as conn:
        # database-design.md 13.3: attempt_count CHECK >= 0
        checks = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid = 'email_outbox'::regclass AND contype = 'c' "
                "AND conname = 'ck_email_outbox_attempt_count_non_negative'"
            )
        )
        # database-design.md 19.11: verification_tokens(expires_at) for the purge
        indexes = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_indexes WHERE tablename = 'verification_tokens' "
                "AND indexname = 'ix_verification_tokens_expires_at_live'"
            )
        )

    assert checks == 1
    assert indexes == 1
