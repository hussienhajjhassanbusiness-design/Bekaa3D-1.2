"""Reference names and slugs at the edge (VS-010 audit A-14): trimmed before their length is
checked, and a name with no visible character is refused."""

import pytest
from pydantic import ValidationError

from app.catalog.api.schemas import (
    MAX_NAME_LENGTH,
    CategoryCreate,
    CategoryUpdate,
    ColourCreate,
    MaterialUpdate,
)


@pytest.mark.parametrize(
    "name", ["\u200b", " \u200b\u200d ", "\ufeff", "\u2060\u00ad", "\u3164", "\u034f\ufe0f"]
)
def test_a_name_of_only_invisible_characters_is_refused(name: str) -> None:
    with pytest.raises(ValidationError, match="visible character"):
        CategoryCreate(name=name, slug="lamps")
    with pytest.raises(ValidationError, match="visible character"):
        MaterialUpdate(name=name)


def test_a_name_with_a_visible_character_keeps_its_joiners() -> None:
    assert ColourCreate(name="Rose \u200dGold").name == "Rose \u200dGold"


def test_a_name_is_trimmed_before_its_length_is_checked() -> None:
    longest = "a" * MAX_NAME_LENGTH
    assert CategoryCreate(name=f"  {longest}  ", slug="lamps").name == longest
    with pytest.raises(ValidationError):
        CategoryCreate(name=longest + "a", slug="lamps")


def test_a_slug_is_trimmed_before_its_length_is_checked() -> None:
    longest = "a" * 200
    assert CategoryCreate(name="Lamps", slug=f" {longest} ").slug.strip() == longest
    assert CategoryUpdate(slug=f"\t{longest}\n") is not None
    with pytest.raises(ValidationError):
        CategoryCreate(name="Lamps", slug="a" * 201)


def test_a_control_character_is_still_refused_before_trimming() -> None:
    with pytest.raises(ValidationError, match="control characters"):
        CategoryCreate(name="\tLamps", slug="lamps")


def test_the_openapi_bounds_are_unchanged() -> None:
    props = CategoryCreate.model_json_schema()["properties"]
    assert (props["name"]["minLength"], props["name"]["maxLength"]) == (1, MAX_NAME_LENGTH)
    assert (props["slug"]["minLength"], props["slug"]["maxLength"]) == (1, 200)
