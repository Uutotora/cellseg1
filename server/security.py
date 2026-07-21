"""Password hashing and opaque-token handling — standard library only.

Two independent concerns live here:

**Passwords** are hashed with :func:`hashlib.scrypt`, a memory-hard KDF that is
in the standard library (no ``bcrypt``/``argon2`` dependency, so this stays in
the light test group). Each hash is self-describing —
``scrypt$n$r$p$salt_b64$hash_b64`` — so the cost parameters travel *with* the
stored value and can be raised over time without a schema change; verifying an
old hash uses that hash's own parameters, and :func:`needs_rehash` reports when
a stored hash predates the current defaults so a caller can transparently
upgrade it on the next successful login.

**Tokens** (login sessions and API keys) are random opaque strings. The raw
token is shown to the client exactly once; the database stores only its SHA-256
hash (:func:`hash_token`). A database leak therefore never exposes a usable
credential, and lookup-by-hash is itself the constant-time comparison (the
attacker can't probe timing on a value they must already know to hash). This is
the same design GitHub and Stripe use for personal-access / API keys.

Nothing here touches a database or the network; it is pure and trivially
unit-tested.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

# ── Password KDF parameters ─────────────────────────────────────────────────
# scrypt cost. n=2**14, r=8, p=1 is a widely used interactive-login setting:
# ~35 ms and ~16 MiB per hash on a modern laptop (measured) — comfortably fast
# for thousands of logins a day, memory-hard enough to make offline cracking of
# a leaked hash expensive. Raise N over the years; old hashes still verify with
# their own stored N, and needs_rehash() flags them for a silent upgrade.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
# scrypt requires maxmem >= 128 * N * r * p bytes; give it generous headroom so
# raising N a notch doesn't start raising ValueError instead.
_SCRYPT_MAXMEM = 128 * 1024 * 1024

# A password longer than this is rejected before hashing. scrypt's cost is
# independent of input length, but an unbounded input is still a needless DoS
# surface (and no human types a 4 KB password).
MAX_PASSWORD_LENGTH = 1024

# Token sizes (bytes of entropy before base64/url-safe encoding).
_SESSION_TOKEN_BYTES = 32       # ~256 bits — session cookies / bearer tokens
_API_KEY_SECRET_BYTES = 24      # ~192 bits — the secret half of an API key
API_KEY_PREFIX = "csk"          # "CellSeg1 Key" — identifies our keys on sight
# The non-secret, displayable head of a key is a *fixed-length slice* of the raw
# string ("csk_" + 8 chars), NOT the substring up to some separator: the url-safe
# token alphabet itself contains "_" and "-", so splitting on a separator would
# be ambiguous. A fixed slice is unambiguous regardless of the token's contents.
_API_KEY_DISPLAY_LEN = len(API_KEY_PREFIX) + 1 + 8   # "csk_" + 8 = 12


def _b64e(raw: bytes) -> str:
    """URL-safe base64 without padding (compact, copy-paste-safe)."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    """Inverse of :func:`_b64e` — restore padding, then decode."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


# ── Passwords ───────────────────────────────────────────────────────────────
def hash_password(
    password: str,
    *,
    n: int = _SCRYPT_N,
    r: int = _SCRYPT_R,
    p: int = _SCRYPT_P,
) -> str:
    """Hash a plaintext password into a self-describing scrypt string.

    Returns ``scrypt$n$r$p$salt$hash`` (both salt and hash url-safe-base64).
    A fresh 16-byte random salt is generated per call, so the same password
    hashes differently every time. Raises ``ValueError`` for an empty or
    over-long password — callers should validate first (see
    :mod:`server.validation`); this is the last-line guard.
    """
    if not password:
        raise ValueError("password must not be empty")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("password too long")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n, r=r, p=p,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return f"scrypt${n}${r}${p}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    """Check a plaintext password against a stored scrypt string.

    Uses the *stored* hash's own cost parameters (not the current defaults), so
    hashes written by an older configuration still verify. Any malformed stored
    value returns ``False`` rather than raising — a corrupt row must fail
    closed, never crash authentication. The comparison is constant-time via
    :func:`hmac.compare_digest`.
    """
    if not password or not encoded:
        return False
    try:
        scheme, n_s, r_s, p_s, salt_s, hash_s = encoded.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = _b64d(salt_s)
        expected = _b64d(hash_s)
    except (ValueError, TypeError):
        return False
    try:
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n, r=r, p=p,
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(dk, expected)


def needs_rehash(encoded: str) -> bool:
    """True if a stored hash was made with weaker-than-current parameters.

    Lets a caller upgrade a password hash transparently on the next successful
    login (verify with the old params, then re-store with the current ones).
    A malformed value returns ``True`` so it gets replaced on next login.
    """
    try:
        scheme, n_s, r_s, p_s, _salt, _hash = encoded.split("$")
        if scheme != "scrypt":
            return True
        return (int(n_s), int(r_s), int(p_s)) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    except (ValueError, TypeError, AttributeError):
        return True


# ── Opaque tokens (sessions) ────────────────────────────────────────────────
def generate_session_token() -> str:
    """A fresh, high-entropy, url-safe session token (the raw secret)."""
    return secrets.token_urlsafe(_SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """The SHA-256 hex digest stored for a raw token.

    Store this, never the raw token. On authentication, hash the presented
    token the same way and look the row up by digest — the lookup itself is the
    constant-time match, and a database dump exposes no usable credential.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── API keys ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NewApiKey:
    """The freshly-minted parts of an API key.

    ``raw`` is returned to the client once and never stored. ``prefix`` is a
    short, non-secret identifier kept in the clear so a key can be shown and
    revoked by name in a UI ("csk_A1b2C3d4…"). ``token_hash`` is what the
    database stores.
    """

    raw: str
    prefix: str
    token_hash: str


def generate_api_key() -> NewApiKey:
    """Mint an API key: ``csk_<secret>``.

    ``prefix`` is the fixed-length, non-secret head of the raw string
    (``csk_`` + the next 8 characters) — displayable and safe to index/store,
    while the full raw string is the bearer credential. Only ``prefix`` and
    ``token_hash`` should ever be persisted.
    """
    secret = secrets.token_urlsafe(_API_KEY_SECRET_BYTES)
    raw = f"{API_KEY_PREFIX}_{secret}"
    return NewApiKey(raw=raw, prefix=raw[:_API_KEY_DISPLAY_LEN], token_hash=hash_token(raw))


def api_key_prefix(raw: str) -> str | None:
    """Return the displayable ``csk_``-prefix head of a raw key, or None.

    Used to reject an obviously-malformed credential early and to look a key up
    cheaply by its indexed prefix. Returns ``None`` if the string isn't shaped
    like one of our keys (wrong scheme, or too short to carry a real secret).
    Deliberately a fixed-length slice, not a separator split — see
    :data:`_API_KEY_DISPLAY_LEN`.
    """
    if not raw.startswith(f"{API_KEY_PREFIX}_") or len(raw) <= _API_KEY_DISPLAY_LEN:
        return None
    return raw[:_API_KEY_DISPLAY_LEN]
