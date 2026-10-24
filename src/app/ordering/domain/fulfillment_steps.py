"""When the customer hears about a physical step (ADR-040 d2): once per order, on the
transition that brings the last live physical line to that step or past it. Pure."""

from collections.abc import Iterable, Sequence

from app.ordering.domain.enums import FulfillmentMethod
from app.ordering.domain.enums import OrderItemStatus as S

# How far along each path a state is; `returned` has shipped but not been delivered.
_RANK: dict[FulfillmentMethod, dict[S, int]] = {
    FulfillmentMethod.DELIVERY: {
        S.PENDING: 0,
        S.IN_PRODUCTION: 1,
        S.READY_TO_SHIP: 2,
        S.SHIPPED: 3,
        S.RETURNED: 3,
        S.DELIVERED: 4,
    },
    FulfillmentMethod.PICKUP: {
        S.PENDING: 0,
        S.IN_PRODUCTION: 1,
        S.READY_FOR_PICKUP: 2,
        S.PICKED_UP: 3,
    },
}
VISIBLE_STEPS: dict[FulfillmentMethod, frozenset[S]] = {
    FulfillmentMethod.DELIVERY: frozenset({S.READY_TO_SHIP, S.SHIPPED, S.DELIVERED}),
    FulfillmentMethod.PICKUP: frozenset({S.READY_FOR_PICKUP, S.PICKED_UP}),
}
# Lines that will never move again are not waited for.
_NOT_WAITED_FOR = frozenset({S.CANCELLED, S.REFUNDED})


def step_reached(method: FulfillmentMethod | None, step: S, physical: Iterable[S]) -> bool:
    """`physical`: every physical line's state after the change. True only for a visible
    step that every live physical line has now reached."""
    if method is None or step not in VISIBLE_STEPS[method]:
        return False
    rank = _RANK[method]
    waited = [s for s in physical if s not in _NOT_WAITED_FOR]
    return bool(waited) and all(rank.get(s, -1) >= rank[step] for s in waited)


def step_newly_reached(
    method: FulfillmentMethod | None, before: Sequence[S], after: Sequence[S]
) -> S | None:
    """A cancel moves no line forward, yet can leave every live line at a step (VS-031):
    the furthest visible step reached now and not before this cancel."""
    if method is None:
        return None
    rank = _RANK[method]
    for step in sorted(VISIBLE_STEPS[method], key=rank.__getitem__, reverse=True):
        if step_reached(method, step, after) and not step_reached(method, step, before):
            return step
    return None
