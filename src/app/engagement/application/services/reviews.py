"""Review create, edit and delete (VS-036 plan 3.3). Lock order: `R_user`, then the
product (FOR NO KEY UPDATE), then the review row; never an order-chain lock (8.1)."""

from uuid import UUID

from app.engagement.application.ports import PurchaseEvidence, ReviewableProducts, ReviewStore
from app.engagement.domain.exceptions import (
    ReviewAlreadyExistsError,
    ReviewContentRejectedError,
    ReviewNotFoundError,
    ReviewProductUnavailableError,
)
from app.engagement.domain.reviews import (
    RATING_MAX,
    RATING_MIN,
    NewReview,
    Review,
    content_refusal,
    normalise_body,
    rating_average,
)


def _checked(rating: int, body: str | None) -> str | None:
    """Every refusal raises here, before any lock or port call."""
    if not RATING_MIN <= rating <= RATING_MAX:
        raise ValueError(f"rating must be between {RATING_MIN} and {RATING_MAX}")
    clean = normalise_body(body)
    refusal = content_refusal(clean)
    if refusal is not None:
        raise ReviewContentRejectedError(refusal.value)
    return clean


async def recompute_rating(
    store: ReviewStore, products: ReviewableProducts, product_id: UUID
) -> None:
    """Exact AVG / COUNT over visible reviews (D7); the caller holds the product lock."""
    ratings_sum, count = await store.visible_totals(product_id)
    await products.set_rating(product_id, rating_average(ratings_sum, count), count)


async def create_review(
    store: ReviewStore,
    products: ReviewableProducts,
    evidence: PurchaseEvidence,
    *,
    user_id: UUID,
    product_id: UUID,
    rating: int,
    body: str | None,
) -> Review:
    clean = _checked(rating, body)
    await store.lock_user(user_id)
    product = await products.lock(product_id)
    if product is None or not product.live or not product.visible:
        raise ReviewProductUnavailableError(product_id)
    if await store.live_for(user_id, product_id) is not None:
        raise ReviewAlreadyExistsError(product_id)
    verified = product_id in await evidence(user_id, [product_id])
    review = await store.insert(NewReview(user_id, product_id, rating, clean, verified))
    await recompute_rating(store, products, product_id)
    return review


async def _lock_own(
    store: ReviewStore, products: ReviewableProducts, *, user_id: UUID, review_id: UUID
) -> Review:
    """`R_user` -> product -> review row; no visibility check (a product hidden later)."""
    await store.lock_user(user_id)
    product_id = await store.own_product_id(review_id, user_id)
    if product_id is None:
        raise ReviewNotFoundError(review_id)
    await products.lock(product_id)
    review = await store.get_own_for_update(review_id, user_id)
    if review is None:
        raise ReviewNotFoundError(review_id)
    return review


async def edit_review(
    store: ReviewStore,
    products: ReviewableProducts,
    evidence: PurchaseEvidence,
    *,
    user_id: UUID,
    review_id: UUID,
    rating: int | None,
    body: str | None,
    body_given: bool,
) -> Review:
    """`body_given` with `body=None` clears the text. A hidden review stays hidden (Q4)."""
    if rating is not None or body_given:
        _checked(rating if rating is not None else RATING_MIN, body if body_given else None)
    current = await _lock_own(store, products, user_id=user_id, review_id=review_id)
    new_rating = current.rating if rating is None else rating
    new_body = normalise_body(body) if body_given else current.body
    verified = current.product_id in await evidence(user_id, [current.product_id])
    review = await store.update(review_id, rating=new_rating, body=new_body, verified=verified)
    await recompute_rating(store, products, current.product_id)
    return review


async def delete_review(
    store: ReviewStore, products: ReviewableProducts, *, user_id: UUID, review_id: UUID
) -> None:
    current = await _lock_own(store, products, user_id=user_id, review_id=review_id)
    await store.soft_delete(review_id)
    await recompute_rating(store, products, current.product_id)
