"""Tests for server.security — password hashing and opaque tokens.

Pure stdlib; runs in the light CI test group (no torch/napari/Qt).
"""
import hashlib

import pytest

from server import security


# ── Password hashing ────────────────────────────────────────────────────────
def test_hash_is_self_describing_and_salted():
    a = security.hash_password("correct horse battery staple")
    b = security.hash_password("correct horse battery staple")
    assert a != b  # random per-call salt => different every time
    assert a.startswith("scrypt$")
    assert a.count("$") == 5  # scheme$n$r$p$salt$hash


def test_verify_roundtrip():
    enc = security.hash_password("s3cret-passphrase")
    assert security.verify_password("s3cret-passphrase", enc) is True
    assert security.verify_password("wrong", enc) is False


def test_verify_rejects_empty_and_malformed():
    enc = security.hash_password("another-password")
    assert security.verify_password("", enc) is False
    assert security.verify_password("x", "") is False
    assert security.verify_password("x", "not-a-hash") is False
    assert security.verify_password("x", "bcrypt$a$b$c$d$e") is False  # wrong scheme
    assert security.verify_password("x", "scrypt$notanint$8$1$aa$bb") is False


def test_hash_rejects_empty_and_overlong():
    with pytest.raises(ValueError):
        security.hash_password("")
    with pytest.raises(ValueError):
        security.hash_password("x" * (security.MAX_PASSWORD_LENGTH + 1))


def test_verify_uses_stored_params_not_current():
    # A hash made with weaker params must still verify (upgrade path).
    weak = security.hash_password("pw", n=2**12)
    assert "scrypt$4096$" in weak
    assert security.verify_password("pw", weak) is True


def test_needs_rehash():
    current = security.hash_password("pw")
    assert security.needs_rehash(current) is False
    weak = security.hash_password("pw", n=2**12)
    assert security.needs_rehash(weak) is True
    assert security.needs_rehash("garbage") is True
    assert security.needs_rehash("bcrypt$x") is True


# ── Session tokens ──────────────────────────────────────────────────────────
def test_session_token_unique_and_hashed():
    t1 = security.generate_session_token()
    t2 = security.generate_session_token()
    assert t1 != t2
    assert len(t1) > 20
    # hash_token is a plain sha256 hex of the raw token
    assert security.hash_token(t1) == hashlib.sha256(t1.encode()).hexdigest()
    assert security.hash_token(t1) != security.hash_token(t2)


# ── API keys ────────────────────────────────────────────────────────────────
def test_api_key_shape_and_hash():
    key = security.generate_api_key()
    assert key.raw.startswith("csk_")
    assert key.prefix.startswith("csk_")
    assert key.raw.startswith(key.prefix)
    # stored hash matches a fresh hash of the raw string
    assert key.token_hash == security.hash_token(key.raw)
    # two mints never collide
    assert security.generate_api_key().raw != key.raw


def test_api_key_prefix_extraction():
    key = security.generate_api_key()
    assert security.api_key_prefix(key.raw) == key.prefix
    assert security.api_key_prefix("nope") is None
    assert security.api_key_prefix("csk_") is None
    assert security.api_key_prefix("other_abc_secret") is None


def test_api_key_prefix_stable_when_secret_contains_underscore(monkeypatch):
    # token_urlsafe's base64url alphabet contains "_", so the displayable prefix
    # must be a fixed-length slice, never a split on "_" (which was a real,
    # ~3%-of-keys bug caught by a flaky run). Force such a secret and assert the
    # prefix is consistent between minting and extraction.
    monkeypatch.setattr(security.secrets, "token_urlsafe", lambda n: "AB_CD_EF_GH_IJ_KL")
    key = security.generate_api_key()
    assert key.raw == "csk_AB_CD_EF_GH_IJ_KL"
    assert key.prefix == "csk_AB_CD_EF"  # first 12 chars, underscores intact
    assert security.api_key_prefix(key.raw) == key.prefix
