import itertools

import pytest

from app.engagement.domain.contact_message import can_transition, check_transition
from app.engagement.domain.enums import ContactMessageStatus as S
from app.engagement.domain.exceptions import InvalidContactMessageTransitionError

ALLOWED = {
    (S.NEW, S.NEW),
    (S.NEW, S.READ),
    (S.NEW, S.REPLIED),
    (S.NEW, S.ARCHIVED),
    (S.READ, S.READ),
    (S.READ, S.REPLIED),
    (S.READ, S.ARCHIVED),
    (S.REPLIED, S.REPLIED),
    (S.REPLIED, S.ARCHIVED),
    (S.ARCHIVED, S.ARCHIVED),
}


@pytest.mark.parametrize(("current", "target"), list(itertools.product(S, S)))
def test_full_transition_matrix(current: S, target: S) -> None:
    expected = (current, target) in ALLOWED
    assert can_transition(current, target) is expected
    if expected:
        check_transition(current, target)
    else:
        with pytest.raises(InvalidContactMessageTransitionError):
            check_transition(current, target)


def test_queue_order_is_declaration_order() -> None:
    # The queue index sorts by the Postgres enum, which follows this order.
    assert [s.value for s in S] == ["new", "read", "replied", "archived"]
