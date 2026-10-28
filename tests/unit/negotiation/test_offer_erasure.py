"""VS-045: account deletion withdraws any live offer, accepted ones too (ADR-047)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.negotiation.application.services.erase_offers import withdraw_live_offers
from app.negotiation.domain.enums import (
    LIVE_STATUSES,
    OfferAction,
    OfferActor,
    OfferStatus,
    OfferTurn,
)
from app.negotiation.domain.exceptions import OfferInvalidTransitionError
from app.negotiation.domain.offers import Offer, withdraw_for_erasure
from tests.unit.negotiation.offer_fakes import USER, FakeStore, make_offer

NOW = datetime(2026, 10, 28, tzinfo=UTC)
_TURNS = {
    OfferStatus.AWAITING_ADMIN: OfferTurn.ADMIN,
    OfferStatus.AWAITING_CUSTOMER: OfferTurn.CUSTOMER,
}


def _offer(status: OfferStatus) -> Offer:
    accepted = status is OfferStatus.ACCEPTED
    return Offer(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        status=status,
        turn=_TURNS.get(status),
        initial_amount_cents=800,
        current_amount_cents=900,
        agreed_amount_cents=900 if accepted else None,
        currency="USD",
        responds_by=None if accepted else NOW + timedelta(days=1),
        accepted_at=NOW if accepted else None,
        checkout_expires_at=NOW + timedelta(days=2) if accepted else None,
        rejected_at=None,
        cooldown_until=None,
        created_at=NOW,
        updated_at=NOW,
        remind_at=NOW if status is OfferStatus.AWAITING_CUSTOMER else None,
    )


@pytest.mark.parametrize("status", sorted(LIVE_STATUSES))
def test_every_live_status_is_withdrawn_by_the_system(status: OfferStatus) -> None:
    later = NOW + timedelta(hours=1)
    withdrawn, round_ = withdraw_for_erasure(_offer(status), next_sequence=4, now=later)
    assert (withdrawn.status, withdrawn.turn, withdrawn.remind_at) == (
        OfferStatus.WITHDRAWN,
        None,
        None,
    )
    assert withdrawn.updated_at == later
    assert (round_.sequence, round_.actor, round_.action) == (
        4,
        OfferActor.SYSTEM,
        OfferAction.WITHDRAWN,
    )
    assert round_.amount_cents is None and round_.message is None


@pytest.mark.parametrize("status", sorted(set(OfferStatus) - LIVE_STATUSES))
def test_a_closed_offer_is_refused(status: OfferStatus) -> None:
    with pytest.raises(OfferInvalidTransitionError):
        withdraw_for_erasure(_offer(status), next_sequence=2, now=NOW)


async def test_the_service_withdraws_only_the_users_live_offers() -> None:
    store = FakeStore()
    mine = [
        make_offer(),
        make_offer(status=OfferStatus.AWAITING_CUSTOMER, turn=OfferTurn.CUSTOMER),
        make_offer(status=OfferStatus.REJECTED, turn=None),
    ]
    theirs = make_offer(user_id=uuid.uuid4())
    for offer in [*mine, theirs]:
        store.offers[offer.id] = offer
    assert await withdraw_live_offers(store, USER, now=NOW) == 2
    statuses = {o.id: o.status for o in store.offers.values()}
    assert [statuses[o.id] for o in mine] == [
        OfferStatus.WITHDRAWN,
        OfferStatus.WITHDRAWN,
        OfferStatus.REJECTED,
    ]
    assert statuses[theirs.id] is OfferStatus.AWAITING_ADMIN
    assert set(store.rounds_by_offer) == {mine[0].id, mine[1].id}
