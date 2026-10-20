"""VS-040's offer transitions (SRS 20.6, FR-13, BR-082 to BR-092; ADR-035), pure domain."""

from dataclasses import replace
from datetime import timedelta

import pytest

from app.negotiation.domain.enums import (
    AWAITING_STATUSES,
    OfferAction,
    OfferActor,
    OfferStatus,
    OfferTurn,
)
from app.negotiation.domain.exceptions import (
    OfferAboveListPriceError,
    OfferAmountChangedError,
    OfferBelowMinimumError,
    OfferExpiredError,
    OfferInvalidTransitionError,
    OfferNotAllowedError,
    OfferNotExpirableError,
    OfferNotYourTurnError,
)
from app.negotiation.domain.offers import (
    MOVES,
    Offer,
    OfferMove,
    accept,
    allowed_moves,
    check_move,
    check_negotiable,
    counter,
    expire,
    expire_checkout,
    is_reminder_due,
    reject,
    reminder_at,
    withdraw,
)
from tests.unit.negotiation.offer_fakes import NOW, STL, make_offer

WINDOW = 48 * 3600
CUSTOMER, ADMIN = OfferActor.CUSTOMER, OfferActor.ADMIN


def _customer_turn(**over: object) -> Offer:
    return make_offer(status=OfferStatus.AWAITING_CUSTOMER, turn=OfferTurn.CUSTOMER, **over)


def _counter(offer: Offer, actor: OfferActor, amount: int, list_price: int = 1000) -> Offer:
    countered, _ = counter(
        offer,
        actor=actor,
        amount_cents=amount,
        message=None,
        list_price_cents=list_price,
        percentage=70,
        response_window_seconds=WINDOW,
        next_sequence=2,
        now=NOW,
    )
    return countered


def _accept(
    offer: Offer, actor: OfferActor, list_price: int = 1000, expected: int | None = None
) -> tuple[Offer, int | None]:
    accepted, round_ = accept(
        offer,
        actor=actor,
        expected_amount_cents=offer.current_amount_cents if expected is None else expected,
        list_price_cents=list_price,
        checkout_window_seconds=3600,
        next_sequence=3,
        now=NOW,
    )
    return accepted, round_.amount_cents


def test_admin_counter_hands_the_turn_to_the_customer_and_arms_the_reminder() -> None:
    offer = make_offer()
    countered, round_ = counter(
        offer,
        actor=ADMIN,
        amount_cents=900,
        message="meet me here",
        list_price_cents=1000,
        percentage=70,
        response_window_seconds=WINDOW,
        next_sequence=2,
        now=NOW,
    )
    assert (countered.status, countered.turn) == (OfferStatus.AWAITING_CUSTOMER, OfferTurn.CUSTOMER)
    assert countered.current_amount_cents == 900
    assert countered.initial_amount_cents == 800
    assert countered.responds_by == NOW + timedelta(seconds=WINDOW)
    assert countered.remind_at == NOW + timedelta(hours=36)
    assert (round_.sequence, round_.actor, round_.action, round_.amount_cents) == (
        2,
        ADMIN,
        OfferAction.COUNTERED,
        900,
    )
    assert (round_.message, round_.currency) == ("meet me here", "USD")


def test_customer_counter_hands_the_turn_back_and_clears_the_reminder() -> None:
    offer = _customer_turn(remind_at=NOW + timedelta(minutes=5))
    countered = _counter(offer, CUSTOMER, 850)
    assert (countered.status, countered.turn) == (OfferStatus.AWAITING_ADMIN, OfferTurn.ADMIN)
    assert countered.responds_by == NOW + timedelta(seconds=WINDOW)
    assert countered.remind_at is None


def test_counters_are_unlimited_and_alternate() -> None:
    """BR-082: twenty rounds later it is still a negotiation."""
    offer = make_offer()
    for _ in range(10):
        offer = _counter(offer, ADMIN, 950)
        offer = _counter(offer, CUSTOMER, 800)
    assert offer.status is OfferStatus.AWAITING_ADMIN


@pytest.mark.parametrize(("amount", "allowed"), [(699, False), (700, True), (1000, True)])
def test_customer_counter_meets_the_floor_and_the_ceiling(amount: int, allowed: bool) -> None:
    if allowed:
        assert _counter(_customer_turn(), CUSTOMER, amount).current_amount_cents == amount
    else:
        with pytest.raises(OfferBelowMinimumError):
            _counter(_customer_turn(), CUSTOMER, amount)


@pytest.mark.parametrize("actor", [ADMIN, CUSTOMER])
def test_no_counter_above_todays_list_price(actor: OfferActor) -> None:
    offer = make_offer() if actor is ADMIN else _customer_turn()
    with pytest.raises(OfferAboveListPriceError):
        _counter(offer, actor, 1001)
    assert _counter(offer, actor, 1000).current_amount_cents == 1000


def test_admin_counter_may_go_below_the_floor() -> None:
    assert _counter(make_offer(), ADMIN, 1).current_amount_cents == 1


@pytest.mark.parametrize("actor", [ADMIN, CUSTOMER])
def test_accept_freezes_the_amount_and_opens_the_checkout_window(actor: OfferActor) -> None:
    offer = make_offer() if actor is ADMIN else _customer_turn(remind_at=NOW)
    accepted, round_amount = _accept(offer, actor)
    assert accepted.status is OfferStatus.ACCEPTED and accepted.turn is None
    assert accepted.agreed_amount_cents == round_amount == 800
    assert (accepted.accepted_at, accepted.checkout_expires_at) == (NOW, NOW + timedelta(hours=1))
    # BR-087: the inactivity timer is void once accepted.
    assert accepted.responds_by is None and accepted.remind_at is None


@pytest.mark.parametrize("actor", [ADMIN, CUSTOMER])
@pytest.mark.parametrize(("list_price", "agreed"), [(700, 700), (799, 799), (800, 800), (900, 800)])
def test_accept_never_agrees_above_todays_list_price(
    actor: OfferActor, list_price: int, agreed: int
) -> None:
    """Owner decision (ADR-035): a price lowered mid-negotiation caps the agreed amount."""
    offer = make_offer() if actor is ADMIN else _customer_turn()
    accepted, round_amount = _accept(offer, actor, list_price=list_price)
    assert accepted.agreed_amount_cents == round_amount == agreed
    assert accepted.current_amount_cents == 800


@pytest.mark.parametrize("actor", [ADMIN, CUSTOMER])
@pytest.mark.parametrize("expected", [799, 801])
def test_accept_refuses_an_amount_no_longer_on_the_table(actor: OfferActor, expected: int) -> None:
    """ADR-035 d9: a stale page cannot bind either party to an amount it never showed."""
    offer = make_offer() if actor is ADMIN else _customer_turn()
    with pytest.raises(OfferAmountChangedError) as caught:
        _accept(offer, actor, expected=expected)
    assert caught.value.current_amount_cents == 800


def test_the_amount_seen_is_the_one_on_the_table_not_the_capped_one() -> None:
    """Under a lowered list price the caller still names `current_amount`, not the cap."""
    assert _accept(make_offer(), ADMIN, list_price=700, expected=800)[1] == 700
    with pytest.raises(OfferAmountChangedError):
        _accept(make_offer(), ADMIN, list_price=700, expected=700)


@pytest.mark.parametrize(("cooldown", "until"), [(600, NOW + timedelta(minutes=10)), (0, NOW)])
def test_reject_arms_the_cooldown(cooldown: int, until: object) -> None:
    rejected, round_ = reject(
        make_offer(), reason="too low", cooldown_seconds=cooldown, next_sequence=2, now=NOW
    )
    assert (rejected.status, rejected.turn) == (OfferStatus.REJECTED, None)
    assert (rejected.rejected_at, rejected.cooldown_until) == (NOW, until)
    assert (round_.actor, round_.action, round_.message, round_.amount_cents) == (
        ADMIN,
        OfferAction.REJECTED,
        "too low",
        None,
    )


@pytest.mark.parametrize("status", sorted(AWAITING_STATUSES))
def test_withdraw_from_either_awaiting_state_whoever_has_the_turn(status: OfferStatus) -> None:
    turn = OfferTurn.ADMIN if status is OfferStatus.AWAITING_ADMIN else OfferTurn.CUSTOMER
    offer = make_offer(status=status, turn=turn, remind_at=None)
    withdrawn, round_ = withdraw(offer, reason=None, next_sequence=2, now=NOW)
    assert (withdrawn.status, withdrawn.turn, withdrawn.remind_at) == (
        OfferStatus.WITHDRAWN,
        None,
        None,
    )
    assert (round_.actor, round_.action) == (CUSTOMER, OfferAction.WITHDRAWN)


@pytest.mark.parametrize(
    ("status", "actor", "move"),
    [
        (OfferStatus.AWAITING_ADMIN, CUSTOMER, OfferMove.COUNTER),
        (OfferStatus.AWAITING_ADMIN, CUSTOMER, OfferMove.ACCEPT),
        (OfferStatus.AWAITING_CUSTOMER, ADMIN, OfferMove.COUNTER),
        (OfferStatus.AWAITING_CUSTOMER, ADMIN, OfferMove.ACCEPT),
        (OfferStatus.AWAITING_CUSTOMER, ADMIN, OfferMove.REJECT),
    ],
)
def test_out_of_turn(status: OfferStatus, actor: OfferActor, move: OfferMove) -> None:
    turn = OfferTurn.ADMIN if status is OfferStatus.AWAITING_ADMIN else OfferTurn.CUSTOMER
    with pytest.raises(OfferNotYourTurnError):
        check_move(make_offer(status=status, turn=turn), actor, move, NOW)


CLOSED = [s for s in OfferStatus if s not in AWAITING_STATUSES and s is not OfferStatus.EXPIRED]
ALL_MOVES = [(actor, move) for actor, moves in MOVES.items() for move in moves]


@pytest.mark.parametrize("status", CLOSED)
@pytest.mark.parametrize(("actor", "move"), ALL_MOVES)
def test_a_closed_or_accepted_offer_cannot_be_answered(
    status: OfferStatus, actor: OfferActor, move: OfferMove
) -> None:
    with pytest.raises(OfferInvalidTransitionError):
        check_move(make_offer(status=status, turn=None), actor, move, NOW)


@pytest.mark.parametrize(("actor", "move"), ALL_MOVES)
def test_an_expired_offer_is_gone(actor: OfferActor, move: OfferMove) -> None:
    offer = make_offer(status=OfferStatus.EXPIRED, turn=None, responds_by=NOW - timedelta(days=1))
    with pytest.raises(OfferExpiredError):
        check_move(offer, actor, move, NOW)


@pytest.mark.parametrize(
    ("actor", "move"), [(CUSTOMER, OfferMove.REJECT), (ADMIN, OfferMove.WITHDRAW)]
)
def test_a_party_cannot_make_the_others_move(actor: OfferActor, move: OfferMove) -> None:
    with pytest.raises(OfferInvalidTransitionError):
        check_move(make_offer(), actor, move, NOW)


@pytest.mark.parametrize(("offset", "expired"), [(-1, False), (0, True), (1, True)])
@pytest.mark.parametrize(("actor", "move"), ALL_MOVES)
def test_the_deadline_is_checked_to_the_second(
    actor: OfferActor, move: OfferMove, offset: int, expired: bool
) -> None:
    """ADR-034 d6: an awaiting offer is over once `now >= responds_by`, job or not."""
    turn_status = OfferStatus.AWAITING_ADMIN if actor is ADMIN else OfferStatus.AWAITING_CUSTOMER
    turn = OfferTurn.ADMIN if actor is ADMIN else OfferTurn.CUSTOMER
    offer = make_offer(status=turn_status, turn=turn, responds_by=NOW)
    at = NOW + timedelta(seconds=offset)
    if expired:
        with pytest.raises(OfferExpiredError):
            check_move(offer, actor, move, at)
    else:
        check_move(offer, actor, move, at)


def test_expiry_outranks_the_turn() -> None:
    """ADR-035 order: a stale offer answers 410 to both parties, never 409."""
    offer = make_offer(responds_by=NOW)
    with pytest.raises(OfferExpiredError):
        check_move(offer, CUSTOMER, OfferMove.COUNTER, NOW)


@pytest.mark.parametrize(
    ("status", "actor", "expected"),
    [
        (OfferStatus.AWAITING_ADMIN, ADMIN, ["counter", "accept", "reject"]),
        (OfferStatus.AWAITING_ADMIN, CUSTOMER, ["withdraw"]),
        (OfferStatus.AWAITING_CUSTOMER, CUSTOMER, ["counter", "accept", "withdraw"]),
        (OfferStatus.AWAITING_CUSTOMER, ADMIN, []),
        (OfferStatus.ACCEPTED, CUSTOMER, []),
        (OfferStatus.REJECTED, ADMIN, []),
    ],
)
def test_allowed_actions(status: OfferStatus, actor: OfferActor, expected: list[str]) -> None:
    turn = {OfferStatus.AWAITING_ADMIN: OfferTurn.ADMIN}.get(status, OfferTurn.CUSTOMER)
    offer = make_offer(status=status, turn=turn if status in AWAITING_STATUSES else None)
    assert [move.value for move in allowed_moves(offer, actor, NOW)] == expected
    assert allowed_moves(replace(offer, responds_by=NOW), actor, NOW) == []


def test_negotiable_needs_a_listed_priced_stl() -> None:
    assert check_negotiable(STL, STL.id) is STL
    for product, reason in [
        (replace(STL, price_cents=0), "not_negotiable"),
        (replace(STL, listed=False), "not_listed"),
        (replace(STL, is_available=False), "unavailable"),
        (None, "not_listed"),
    ]:
        with pytest.raises(OfferNotAllowedError) as caught:
            check_negotiable(product, STL.id)
        assert caught.value.reason == reason


def test_reminder_falls_at_three_quarters_of_the_turn() -> None:
    assert reminder_at(NOW, NOW + timedelta(hours=48)) == NOW + timedelta(hours=36)
    assert reminder_at(NOW, NOW + timedelta(hours=1)) == NOW + timedelta(minutes=45)


@pytest.mark.parametrize(("offset", "due"), [(-1, False), (0, True), (1, True)])
def test_reminder_due_from_remind_at(offset: int, due: bool) -> None:
    offer = _customer_turn(remind_at=NOW, responds_by=NOW + timedelta(hours=1))
    assert is_reminder_due(offer, NOW + timedelta(seconds=offset)) is due


def test_no_reminder_once_the_deadline_is_reached() -> None:
    offer = _customer_turn(remind_at=NOW - timedelta(minutes=1), responds_by=NOW)
    assert not is_reminder_due(offer, NOW)


def test_expiry_clears_the_reminder() -> None:
    """`ck_offers_remind_at_awaiting_customer` would refuse an expired row that kept it."""
    offer = _customer_turn(responds_by=NOW, remind_at=NOW - timedelta(minutes=5))
    expired, _ = expire(offer, next_sequence=2, now=NOW)
    assert expired.remind_at is None


def _accepted(expires_in: int) -> Offer:
    return make_offer(
        status=OfferStatus.ACCEPTED,
        turn=None,
        responds_by=None,
        agreed_amount_cents=800,
        accepted_at=NOW - timedelta(hours=1),
        checkout_expires_at=NOW + timedelta(seconds=expires_in),
    )


@pytest.mark.parametrize(("expires_in", "over"), [(1, False), (0, True), (-1, True)])
def test_checkout_window_closes_at_its_deadline(expires_in: int, over: bool) -> None:
    offer = _accepted(expires_in)
    if not over:
        with pytest.raises(OfferNotExpirableError):
            expire_checkout(offer, next_sequence=3, now=NOW)
        return
    closed, round_ = expire_checkout(offer, next_sequence=3, now=NOW)
    assert closed.status is OfferStatus.CHECKOUT_EXPIRED
    assert (closed.agreed_amount_cents, closed.checkout_expires_at) == (
        800,
        offer.checkout_expires_at,
    )
    assert (round_.actor, round_.action) == (OfferActor.SYSTEM, OfferAction.CHECKOUT_EXPIRED)


def test_an_accepted_offer_never_expires_from_inactivity() -> None:
    """BR-087, even with a stale deadline left on the row."""
    offer = replace(_accepted(3600), responds_by=NOW - timedelta(days=1))
    with pytest.raises(OfferNotExpirableError):
        expire(offer, next_sequence=3, now=NOW)
