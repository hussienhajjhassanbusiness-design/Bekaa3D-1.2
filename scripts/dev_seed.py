"""Local-development seed for the frontend team (docs/frontend-handoff/README.md).
Refuses to run unless ENVIRONMENT is development or test. Credentials are generated
at run time and printed once; none is ever written to a file."""

import argparse
import asyncio
import io
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.commands.category_admin import CreateCategory
from app.catalog.application.commands.product_admin import CreateProduct
from app.catalog.application.commands.product_image_admin import UploadProductImage
from app.catalog.application.commands.value_admin import CreateReferenceValue
from app.catalog.domain.entities import Colour, Material
from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.product import Dimensions, ProductAttributes
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.catalog.infrastructure.product_repository import ProductRepository
from app.catalog.infrastructure.repositories import (
    CategoryRepository,
    ColourRepository,
    MaterialRepository,
    SqlReferenceLocks,
)
from app.core import models as _models  # noqa: F401 - registers every table on Base.metadata
from app.core.config import get_settings
from app.core.database import make_engine, make_session_factory
from app.engagement.public import NotificationType, create_notification
from app.identity.application.security.password_hasher import hash_password
from app.identity.application.security.secret_cipher import encrypt_secret
from app.identity.application.security.token_service import hash_token
from app.identity.application.security.totp import generate_secret, provisioning_uri
from app.identity.domain.enums import MfaMethod, UserRole
from app.identity.domain.recovery_codes import generate_code_set, normalize_code
from app.identity.infrastructure.models import UserModel
from app.identity.infrastructure.repositories import (
    MfaCredentialRepository,
    MfaRecoveryCodeRepository,
    SessionRepository,
)
from app.integrations.images.factory import get_image_sanitizer
from app.integrations.scanning.fake import FakeScanner
from app.integrations.storage.factory import public_media_storage
from app.platform.application.commands.update_setting import UpdateSetting
from app.platform.domain.exceptions import InvalidSettingValueError
from app.platform.domain.settings_registry import SettingValue
from app.platform.infrastructure.repositories import AuditLogRepository, SettingRepository
from app.platform.public import SqlAuditWriter

ALLOWED_ENVIRONMENTS = frozenset({"development", "test"})
ADMIN_EMAIL = "seed-admin@example.com"
CUSTOMER_EMAIL = "seed-customer@example.com"

CATEGORIES = (
    ("Home Decor", "home-decor", True),
    ("Toys and Figures", "toys-figures", True),
    ("Tools and Gadgets", "tools-gadgets", True),
    # Disabled on purpose: its product must never reach the storefront.
    ("Seasonal", "seasonal", False),
)
# The one product seeded with a second image, to exercise a gallery.
GALLERY_SLUG = "dragon"
MATERIALS = ("PLA", "PETG", "Resin")
COLOURS = ("Black", "White", "Red")


@dataclass(frozen=True)
class ProductSpec:
    slug: str
    name: str
    category: str
    price_cents: int
    material: str | None = None
    colour: str | None = None
    purchase_mode: PurchaseMode | None = None
    visible: bool = True
    available: bool = True
    featured: bool = False
    images: int = 1

    @property
    def type(self) -> ProductType:
        return ProductType.STL if self.purchase_mode is None else ProductType.PHYSICAL


def _physical(
    slug: str,
    name: str,
    category: str,
    price_cents: int,
    made_of: str,
    mode: str,
    *,
    visible: bool = True,
    available: bool = True,
    featured: bool = False,
) -> ProductSpec:
    material, colour = made_of.split("/")
    purchase_mode = PurchaseMode(mode)
    return ProductSpec(
        slug,
        name,
        category,
        price_cents,
        material,
        colour,
        purchase_mode,
        visible,
        available,
        featured,
    )


PRODUCTS = (
    _physical("moon-lamp", "Moon Lamp", "home-decor", 2400, "PLA/White", "both", featured=True),
    _physical("geometric-planter", "Geometric Planter", "home-decor", 1250, "PETG/Black", "both"),
    _physical("dragon", "Articulated Dragon", "toys-figures", 1800, "PLA/Red", "both"),
    _physical(
        "cable-organizer", "Cable Organizer", "tools-gadgets", 600, "PETG/Black", "online_only"
    ),
    _physical("name-sign", "Custom Name Sign", "home-decor", 3000, "PLA/Red", "whatsapp_only"),
    _physical(
        "knight", "Miniature Knight", "toys-figures", 999, "Resin/White", "both", available=False
    ),
    ProductSpec("dragon-stl", "Articulated Dragon STL", "toys-figures", 700),
    ProductSpec("phone-stand-stl", "Phone Stand STL", "tools-gadgets", 350, featured=True),
    ProductSpec("low-poly-vase-stl", "Low-Poly Vase STL", "home-decor", 400, available=False),
    # Hidden, and in a disabled category: neither may appear on the storefront.
    _physical(
        "prototype-gear",
        "Prototype Gear",
        "tools-gadgets",
        500,
        "PETG/Black",
        "both",
        visible=False,
    ),
    _physical("holiday-ornament", "Holiday Ornament", "seasonal", 800, "PLA/Red", "both"),
)


class AuditContext(TypedDict):
    actor_user_id: UUID
    request_id: str | None
    ip_hash: str | None


def _acting_as(actor: UUID) -> AuditContext:
    return {"actor_user_id": actor, "request_id": None, "ip_hash": None}


@dataclass
class SeedReport:
    issued: dict[str, str] = field(default_factory=dict)
    reference_ids: list[UUID] = field(default_factory=list)
    products_created: int = 0
    images_created: int = 0


def ensure_dev_environment() -> None:
    """An allowlist, not `!= production`: ENVIRONMENT is free text, so `prod` must not pass."""
    environment = get_settings().environment
    if environment not in ALLOWED_ENVIRONMENTS:
        raise SystemExit(f"dev_seed refuses to run with ENVIRONMENT={environment!r}.")


async def _account(
    session: AsyncSession, email: str, role: UserRole, *, rotate: bool
) -> tuple[UserModel, str | None, bool]:
    """The account, its new password when one was issued on this run, and whether it is new."""
    user = await session.scalar(
        select(UserModel).where(UserModel.email == email, UserModel.deleted_at.is_(None))
    )
    if user is not None and not rotate:
        return user, None, False
    created = user is None
    password = secrets.token_urlsafe(18)
    now = datetime.now(UTC)
    if user is None:
        user = UserModel(email=email, role=role, email_verified_at=now)
        session.add(user)
    else:
        # Void everything issued under the old password (ADR-018).
        user.auth_epoch += 1
        await SessionRepository(session).revoke_all_for_user(user_id=user.id, at=now)
    user.password_hash = hash_password(password)
    user.is_active = True
    await session.flush()
    return user, password, created


async def _enrol_mfa(session: AsyncSession, user: UserModel) -> tuple[str, list[str]]:
    """Enable TOTP as `/auth/mfa/setup/confirm` would; returns the secret and recovery codes."""
    credentials, recovery = MfaCredentialRepository(session), MfaRecoveryCodeRepository(session)
    secret = generate_secret()
    ciphertext = encrypt_secret(secret)
    credential = await credentials.get_by_user_id_for_update(user.id)
    if credential is None:
        credential = await credentials.add(
            user_id=user.id, method=MfaMethod.TOTP, secret_ciphertext=ciphertext
        )
    credential.secret_ciphertext = ciphertext
    # A new secret has spent no step; a stale mark would reject its first code as a replay.
    credential.last_totp_step = None
    credential.enable(datetime.now(UTC))
    await credentials.save(credential)
    await recovery.delete_unused(credential.id)
    codes = generate_code_set()
    await recovery.add_set(
        mfa_credential_id=credential.id,
        code_hashes=[hash_token(normalize_code(code)) for code in codes],
    )
    return secret, codes


async def _accounts(session: AsyncSession, report: SeedReport, *, rotate: bool) -> UserModel:
    admin, admin_password, _ = await _account(session, ADMIN_EMAIL, UserRole.ADMIN, rotate=rotate)
    if admin_password is not None:
        secret, codes = await _enrol_mfa(session, admin)
        report.issued |= {
            "admin password": admin_password,
            "admin TOTP secret": secret,
            "admin otpauth URI": provisioning_uri(secret=secret, account_name=ADMIN_EMAIL),
            "admin recovery codes": " ".join(codes),
        }
    customer, password, created = await _account(
        session, CUSTOMER_EMAIL, UserRole.CUSTOMER, rotate=rotate
    )
    if password is not None:
        report.issued["customer password"] = password
    for event in ("account.seed_welcome", "account.seed_reminder") if created else ():
        await create_notification(
            session,
            user_id=customer.id,
            notification_type=NotificationType.ACCOUNT,
            payload={"event": event, "message": "Created by scripts/dev_seed.py."},
        )
    return admin


async def _reference_data(
    session: AsyncSession, actor: UUID, report: SeedReport
) -> tuple[dict[str, UUID], dict[str, UUID], dict[str, UUID]]:
    """Get-or-create by live slug or name, so a second run adds nothing."""
    audit = SqlAuditWriter(session)
    context = _acting_as(actor)
    categories: dict[str, UUID] = {}
    for name, slug, active in CATEGORIES:
        found = await session.scalar(
            select(CategoryModel.id).where(
                CategoryModel.slug == slug, CategoryModel.deleted_at.is_(None)
            )
        )
        if found is None:
            created = await CreateCategory(CategoryRepository(session), audit).execute(
                name=name, slug=slug, is_active=active, **context
            )
            found = created.id
            report.reference_ids.append(found)
        categories[slug] = found
    materials: dict[str, UUID] = {}
    for name in MATERIALS:
        found = await session.scalar(
            select(MaterialModel.id).where(
                func.lower(MaterialModel.name) == name.lower(), MaterialModel.deleted_at.is_(None)
            )
        )
        if found is None:
            material = await CreateReferenceValue[Material](
                MaterialRepository(session), audit, entity_type="Material"
            ).execute(name=name, is_active=True, **context)
            found = material.id
            report.reference_ids.append(found)
        materials[name] = found
    colours: dict[str, UUID] = {}
    for name in COLOURS:
        found = await session.scalar(
            select(ColourModel.id).where(
                func.lower(ColourModel.name) == name.lower(), ColourModel.deleted_at.is_(None)
            )
        )
        if found is None:
            colour = await CreateReferenceValue[Colour](
                ColourRepository(session), audit, entity_type="Colour"
            ).execute(name=name, is_active=True, **context)
            found = colour.id
            report.reference_ids.append(found)
        colours[name] = found
    return categories, materials, colours


def _attributes(
    spec: ProductSpec,
    categories: dict[str, UUID],
    materials: dict[str, UUID],
    colours: dict[str, UUID],
) -> ProductAttributes:
    physical = spec.type is ProductType.PHYSICAL
    return ProductAttributes(
        category_id=categories[spec.category],
        name=spec.name,
        slug=spec.slug,
        price_cents=spec.price_cents,
        description=f"{spec.name}: seeded by scripts/dev_seed.py for local testing.",
        is_visible=spec.visible,
        is_featured=spec.featured,
        is_available=spec.available,
        purchase_mode=spec.purchase_mode,
        material_id=materials[spec.material] if spec.material else None,
        colour_id=colours[spec.colour] if spec.colour else None,
        dimensions=Dimensions(120, 80, 60) if physical else None,
        production_lead_time_days=2 if physical else None,
        batch_size=2 if physical else None,
        max_quantity_per_line=5 if physical else None,
    )


def _png(shade: int) -> bytes:
    colour = ((shade * 67) % 256, (shade * 131) % 256, (shade * 199) % 256)
    out = io.BytesIO()
    Image.new("RGB", (800, 800), colour).save(out, format="PNG")
    return out.getvalue()


async def _catalogue(session: AsyncSession, actor: UUID, report: SeedReport) -> None:
    categories, materials, colours = await _reference_data(session, actor, report)
    audit, products = SqlAuditWriter(session), ProductRepository(session)
    create = CreateProduct(products, SqlReferenceLocks(session), audit)
    # The fake scanner: these bytes are generated above, and ClamAV may not be running.
    upload = UploadProductImage(
        products,
        ProductImageRepository(session),
        audit,
        storage=public_media_storage(get_settings()),
        scanner=FakeScanner(),
        sanitizer=get_image_sanitizer(),
    )
    context = _acting_as(actor)
    for index, spec in enumerate(PRODUCTS):
        live = select(ProductModel.id).where(
            ProductModel.slug == spec.slug, ProductModel.deleted_at.is_(None)
        )
        if await session.scalar(live) is not None:
            continue
        product = await create.execute(
            product_type=spec.type,
            attributes=_attributes(spec, categories, materials, colours),
            **context,
        )
        report.products_created += 1
        for number in range(spec.images + (spec.slug == GALLERY_SLUG)):
            await upload.execute(
                product_id=product.id,
                data=_png(index * 3 + number + 1),
                alt_text=f"{spec.name}, view {number + 1}",
                **context,
            )
            report.images_created += 1


async def seed(
    session: AsyncSession, *, rotate: bool = False, whatsapp_number: str | None = None
) -> SeedReport:
    """Idempotent: existing accounts, reference values and products are left as they are."""
    ensure_dev_environment()
    report = SeedReport()
    admin = await _accounts(session, report, rotate=rotate)
    await _catalogue(session, admin.id, report)
    values: dict[str, SettingValue] = {"accepting_orders": True}
    if whatsapp_number:
        values["whatsapp_number"] = whatsapp_number
    update = UpdateSetting(SettingRepository(session), AuditLogRepository(session))
    for key, value in values.items():
        await update.execute(key=key, value=value, **_acting_as(admin.id))
    return report


async def _run(arguments: argparse.Namespace) -> SeedReport:
    engine = make_engine(get_settings().database_url)
    try:
        async with make_session_factory(engine)() as session:
            report = await seed(
                session,
                rotate=arguments.rotate_credentials,
                whatsapp_number=arguments.whatsapp_number,
            )
            await session.commit()
            return report
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotate-credentials",
        action="store_true",
        help="issue new passwords, TOTP secret and recovery codes for the seed accounts",
    )
    parser.add_argument("--whatsapp-number", help="E.164, e.g. +96170123456; sets the setting")
    ensure_dev_environment()
    try:
        report = asyncio.run(_run(parser.parse_args()))
    except InvalidSettingValueError as exc:
        raise SystemExit(f"--whatsapp-number rejected: {exc}") from exc
    print(f"Accounts: {ADMIN_EMAIL} (administrator, MFA enrolled) and {CUSTOMER_EMAIL}")
    for label, value in report.issued.items():
        print(f"  {label:<22}{value}")
    if report.issued:
        print("Shown once: keep these in a password manager, never in a tracked file.")
    else:
        print("  Both accounts already exist; --rotate-credentials issues new credentials.")
    print(f"Created {report.products_created} products and {report.images_created} images.")


if __name__ == "__main__":
    main()
