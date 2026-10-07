from uuid import uuid4

from app.core.security import csrf_token_for_session, verify_csrf_token


def test_the_same_session_always_derives_the_same_token() -> None:
    session_id = uuid4()

    assert csrf_token_for_session(session_id) == csrf_token_for_session(session_id)


def test_different_sessions_derive_different_tokens() -> None:
    """This binding is what stops a cookie-injection attacker from supplying
    their own matching cookie/header pair for someone else's session."""
    assert csrf_token_for_session(uuid4()) != csrf_token_for_session(uuid4())


def test_verify_accepts_the_matching_token() -> None:
    session_id = uuid4()

    assert verify_csrf_token(session_id=session_id, presented=csrf_token_for_session(session_id))


def test_verify_rejects_another_sessions_token() -> None:
    assert not verify_csrf_token(session_id=uuid4(), presented=csrf_token_for_session(uuid4()))


def test_verify_rejects_a_missing_token() -> None:
    session_id = uuid4()

    assert not verify_csrf_token(session_id=session_id, presented=None)
    assert not verify_csrf_token(session_id=session_id, presented="")
