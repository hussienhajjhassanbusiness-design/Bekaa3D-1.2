"""VS-034 / SRS 13.2: the Bring Your Idea fields and their limits."""

from typing import Any

import pytest

from app.engagement.domain.custom_request import (
    DESCRIPTION_MAX,
    DIMENSIONS_MAX,
    NAME_MAX,
    PREFERENCE_MAX,
    TITLE_MAX,
    CustomRequestDetails,
)
from app.engagement.domain.exceptions import InvalidCustomRequestError


def _fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "name": "Rima Haddad",
        "email": "rima@example.com",
        "phone": "+961 3 123 456",
        "project_title": "Cedar lamp",
        "description": "A lamp shaped like a cedar.\nAbout 30 cm tall.",
        "preferred_material": "PLA",
        "preferred_colour": "Green",
        "dimensions": "30 x 20 x 20 cm",
    }
    return fields | overrides


def test_fields_are_trimmed_and_blank_optionals_become_none() -> None:
    details = CustomRequestDetails.of(
        **_fields(
            name="  Rima ",
            project_title=" Lamp ",
            preferred_material="  ",
            preferred_colour="",
            dimensions=None,
        )
    )
    assert (details.name, details.project_title) == ("Rima", "Lamp")
    assert (details.preferred_material, details.preferred_colour, details.dimensions) == (
        None,
        None,
        None,
    )
    assert details.description.count("\n") == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "   "),
        ("name", "x" * (NAME_MAX + 1)),
        ("email", "no-at-sign"),
        ("email", "@example.com"),
        ("phone", ""),
        ("phone", "12345"),
        ("phone", "call me maybe"),
        ("phone", "1" * 33),
        ("project_title", " "),
        ("project_title", "x" * (TITLE_MAX + 1)),
        ("description", ""),
        ("description", "x" * (DESCRIPTION_MAX + 1)),
        ("preferred_material", "x" * (PREFERENCE_MAX + 1)),
        ("preferred_colour", "x" * (PREFERENCE_MAX + 1)),
        ("dimensions", "x" * (DIMENSIONS_MAX + 1)),
    ],
)
def test_each_invalid_field_is_named_without_its_value(field: str, value: str) -> None:
    with pytest.raises(InvalidCustomRequestError) as caught:
        CustomRequestDetails.of(**_fields(**{field: value}))
    assert caught.value.fields == [field]
    if value.strip():
        assert value not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "most"),
    [
        ("name", NAME_MAX),
        ("project_title", TITLE_MAX),
        ("description", DESCRIPTION_MAX),
        ("preferred_material", PREFERENCE_MAX),
        ("preferred_colour", PREFERENCE_MAX),
        ("dimensions", DIMENSIONS_MAX),
    ],
)
def test_every_limit_is_inclusive(field: str, most: int) -> None:
    details = CustomRequestDetails.of(**_fields(**{field: "x" * most}))
    assert getattr(details, field) == "x" * most


def test_several_bad_fields_are_all_reported() -> None:
    with pytest.raises(InvalidCustomRequestError) as caught:
        CustomRequestDetails.of(**_fields(name="", phone="x", dimensions="y" * 500))
    assert caught.value.fields == ["name", "phone", "dimensions"]
