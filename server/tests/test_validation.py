"""Tests for server.validation — normalisation and rejection."""
import pytest

from server import validation
from server.errors import ValidationError


def test_email_normalised():
    assert validation.validate_email("  Alice@Example.COM ") == "alice@example.com"


@pytest.mark.parametrize("bad", ["", "  ", "no-at-sign", "a@b", "a@@b.com", "a b@c.com", None])
def test_email_rejects(bad):
    with pytest.raises(ValidationError) as ei:
        validation.validate_email(bad)
    assert ei.value.field == "email"


def test_username_normalised_and_rules():
    assert validation.validate_username("  Alice_01 ") == "alice_01"
    for good in ["abc", "a.b-c_d", "user01"]:
        assert validation.validate_username(good) == good


@pytest.mark.parametrize("bad", ["", "ab", "-abc", ".abc", "a" * 33, "has space", "emoji😀x", None])
def test_username_rejects(bad):
    with pytest.raises(ValidationError) as ei:
        validation.validate_username(bad)
    assert ei.value.field == "username"


def test_password_length_policy():
    assert validation.validate_password("longenough") == "longenough"
    # spaces are legitimate and preserved (not stripped)
    assert validation.validate_password("  spaced  ") == "  spaced  "
    with pytest.raises(ValidationError):
        validation.validate_password("short")
    with pytest.raises(ValidationError):
        validation.validate_password("x" * (validation.MAX_PASSWORD_LENGTH + 1))


def test_name_validation():
    assert validation.validate_name("  My Lab  ") == "My Lab"
    with pytest.raises(ValidationError) as ei:
        validation.validate_name("   ", field="org_name")
    assert ei.value.field == "org_name"
    with pytest.raises(ValidationError):
        validation.validate_name("x" * 5, max_length=3)


def test_slugify():
    assert validation.slugify("Fluorescence Nuclei (DAPI)") == "fluorescence-nuclei-dapi"
    assert validation.slugify("   ") == "item"
    assert validation.slugify("!!!") == "item"
    assert validation.slugify("Already-Slug") == "already-slug"
