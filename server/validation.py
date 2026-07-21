"""Input validation for user-supplied fields — standard library only.

Every function either returns the *normalised* value or raises
:class:`server.errors.ValidationError` with the offending ``field`` set, so a
service method can validate and get a clean, canonical value in one call
(``email = validate_email(raw)``) and the future API tier can turn the
exception straight into a 422 body.

Normalisation matters as much as rejection: emails and usernames are lowercased
and stripped so that "Alice@Example.com " and "alice@example.com" can't become
two different accounts — the uniqueness guarantees in the database only hold if
the values are canonicalised *before* they are stored or compared.
"""
from __future__ import annotations

import re

from .errors import ValidationError

# A deliberately pragmatic email check: one @, non-empty local part, a dotted
# domain. Full RFC 5322 is famously not a regex; this rejects the obvious
# garbage and defers real "can this receive mail" proof to a verification email
# (a later feature), which is the only check that actually means anything.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Usernames: a handle, not a display name. Lowercase letters/digits and a few
# separators, must start with an alphanumeric. 3–32 chars.
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024  # mirrors security.MAX_PASSWORD_LENGTH


def validate_email(value: str) -> str:
    """Return the normalised (stripped, lowercased) email or raise.

    Lowercasing is what makes the DB's unique constraint meaningful: without
    it, two rows differing only in case would both be insertable.
    """
    if not isinstance(value, str):
        raise ValidationError("Email is required.", field="email")
    email = value.strip().lower()
    if not email:
        raise ValidationError("Email is required.", field="email")
    if len(email) > 320:  # 64 local + @ + 255 domain, the practical RFC ceiling
        raise ValidationError("Email is too long.", field="email")
    if not _EMAIL_RE.match(email):
        raise ValidationError("Enter a valid email address.", field="email")
    return email


def validate_username(value: str) -> str:
    """Return the normalised (stripped, lowercased) username or raise."""
    if not isinstance(value, str):
        raise ValidationError("Username is required.", field="username")
    username = value.strip().lower()
    if not username:
        raise ValidationError("Username is required.", field="username")
    if not _USERNAME_RE.match(username):
        raise ValidationError(
            "Username must be 3–32 characters: letters, digits, and . _ - "
            "(starting with a letter or digit).",
            field="username",
        )
    return username


def validate_password(value: str) -> str:
    """Return the password unchanged if acceptable, else raise.

    Length-only policy on purpose: NIST 800-63B guidance is that a length floor
    plus a breached-password check beats composition rules (which mostly push
    users toward predictable "P@ssw0rd!" patterns). The breach check is a later
    feature; the floor is enforced here. The password is *not* stripped or
    altered — leading/trailing spaces are legitimate password characters.
    """
    if not isinstance(value, str):
        raise ValidationError("Password is required.", field="password")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            field="password",
        )
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValidationError("Password is too long.", field="password")
    return value


def validate_name(value: str, *, field: str = "name", max_length: int = 200) -> str:
    """Validate a human-facing name (org name, project name, full name).

    Trimmed; must be non-empty and within ``max_length``. Unlike a slug or
    username this keeps case, spaces, and unicode — it's a label, not an id.
    """
    if not isinstance(value, str):
        raise ValidationError("A name is required.", field=field)
    name = value.strip()
    if not name:
        raise ValidationError("A name is required.", field=field)
    if len(name) > max_length:
        raise ValidationError(f"Name is too long (max {max_length}).", field=field)
    return name


def slugify(name: str) -> str:
    """Turn a human name into a url/filesystem-safe slug.

    Lowercased, non-alphanumerics collapsed to single hyphens, trimmed. Falls
    back to ``"item"`` for an empty or all-symbol input so a slug is always
    non-empty (the store layers append ``-2``, ``-3`` … to resolve collisions).
    Deliberately identical in spirit to ``studio.project.slugify`` so the two
    layers produce the same ids for the same names.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "item"
