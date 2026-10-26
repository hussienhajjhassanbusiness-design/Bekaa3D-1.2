"""The review profanity list (VS-036 plan 3.1, Q5): English, Arabic and Arabizi.
Matched as whole words after NFKC and casefold; the owner approves changes here."""

from typing import Final

PROFANITY_WORDS: Final = frozenset(
    {
        # English
        "fuck",
        "fucking",
        "fucker",
        "motherfucker",
        "shit",
        "bullshit",
        "bitch",
        "cunt",
        "asshole",
        "bastard",
        "dick",
        "whore",
        "slut",
        # Arabic
        "كس",
        "كسمك",
        "شرموطة",
        "شرموطه",
        "عرص",
        "منيك",
        "زب",
        "قحبة",
        "قحبه",
        # Arabizi
        "kos",
        "kuss",
        "kosomak",
        "sharmouta",
        "sharmoota",
        "sharmota",
        "3ars",
        "manyak",
        "ayre",
        "ayri",
        "zeb",
        "a7ba",
        "2a7ba",
    }
)
