"""Review rate limits (VS-036 plan 5, Q6): code constants, not settings."""

from typing import Final

# One bucket per user, shared by POST, PATCH and DELETE.
REVIEW_WRITE_LIMIT: Final = 10
REVIEW_WRITE_WINDOW_SECONDS: Final = 3600
# The public list, per IP; the same budget as the other public catalogue reads.
REVIEW_READ_LIMIT: Final = 600
REVIEW_READ_WINDOW_SECONDS: Final = 3600
