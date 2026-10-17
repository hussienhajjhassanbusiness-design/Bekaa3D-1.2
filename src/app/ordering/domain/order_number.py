"""Human-readable order numbers (BR-032; VS-023 plan Q11): `B3D-` and 8 Crockford base32
characters from 40 random bits, so the number reveals nothing about sales volume."""

import secrets
from collections.abc import Callable

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIX = "B3D-"


def new_order_number(random_bytes: Callable[[int], bytes] = secrets.token_bytes) -> str:
    value = int.from_bytes(random_bytes(5), "big")
    chars = [CROCKFORD[(value >> shift) & 0x1F] for shift in range(35, -1, -5)]
    return PREFIX + "".join(chars)
